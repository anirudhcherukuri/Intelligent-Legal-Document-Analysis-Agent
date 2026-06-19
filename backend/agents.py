import json
import os
from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from backend.schemas import ExtractedClause, RiskAnalysis, ComparisonItem
from backend.config import LLM_MODEL, OPENAI_API_KEY, PLAYBOOK_PATH

# Define LangGraph State
class GraphState(TypedDict):
    contract_text: str
    contract_type: str  # NDA, SaaS_Agreement, Employment_Agreement, or General
    extracted_clauses: List[ExtractedClause]
    risk_analysis: List[RiskAnalysis]
    comparison_results: List[ComparisonItem]
    current_step: str
    overall_risk_score: Optional[str]
    summary: Optional[str]
    error: Optional[str]

# Pydantic wrapper classes for structured LLM outputs
class ExtractedClausesContainer(BaseModel):
    contract_type: str = Field(description="The classified type of the contract: NDA, SaaS_Agreement, Employment_Agreement, or General.")
    clauses: List[ExtractedClause] = Field(description="List of extracted clauses from the contract text.")

class RiskAnalysisContainer(BaseModel):
    risks: List[RiskAnalysis] = Field(description="Risk assessment list for the contract clauses.")

class ComparisonContainer(BaseModel):
    comparisons: List[ComparisonItem] = Field(description="Comparison checklist against standard playbook.")
    overall_risk_score: str = Field(description="Overall risk profile: Low, Medium, or High.")
    summary: str = Field(description="A 2-3 sentence executive summary of the legal review.")

# Helper to load the playbook
def get_playbook() -> Dict[str, Any]:
    try:
        if os.path.exists(PLAYBOOK_PATH):
            with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading playbook: {e}")
    return {"contract_types": {}}

# Helper to get the ChatOpenAI client
def get_llm():
    api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_openai_api_key_here":
        raise ValueError("API Key is missing. Please set it in your environment or Settings.")
    
    if api_key.startswith("gsk_"):
        return ChatOpenAI(
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
    
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=0.0,
        api_key=api_key
    )

# ==========================================
# Agent Nodes
# ==========================================

def extractor_node(state: GraphState) -> Dict[str, Any]:
    """Extractor Agent: Analyzes raw text and extracts key legal clauses."""
    print("Executing Extractor Agent...")
    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(ExtractedClausesContainer)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an elite legal contract examiner. Your job is to classify the contract type and extract core clauses. "
                       "Look for important legal terms such as Confidentiality, Liability Caps, Indemnification, Governing Law, Term and Termination, Non-Competes, etc. "
                       "Provide the exact clause text, specify the page number if mentioned (estimate based on paragraphs if not explicit), and evaluate your confidence score."),
            ("user", "Analyze the contract text below and extract all major clauses.\n\nContract Text:\n{contract_text}")
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({"contract_text": state["contract_text"]})
        
        # Handle dict or Pydantic result object due to provider variations (OpenAI vs Groq)
        if isinstance(result, dict):
            contract_type_val = result.get("contract_type", state.get("contract_type", "General"))
            clauses_raw = result.get("clauses", [])
            extracted_clauses = []
            for c in clauses_raw:
                if isinstance(c, dict):
                    extracted_clauses.append(ExtractedClause(**c))
                else:
                    extracted_clauses.append(c)
        else:
            contract_type_val = result.contract_type
            extracted_clauses = result.clauses

        return {
            "contract_type": contract_type_val,
            "extracted_clauses": extracted_clauses,
            "current_step": "risk_analyzer",
            "error": None
        }
    except Exception as e:
        print(f"Extractor Agent error: {e}")
        return {
            "current_step": "end",
            "error": f"Extractor failed: {str(e)}"
        }

def risk_analyzer_node(state: GraphState) -> Dict[str, Any]:
    """Risk Analyzer Agent: Evaluates extracted clauses for legal liabilities and omissions."""
    print("Executing Risk Analyzer Agent...")
    if state.get("error"):
        return state
        
    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(RiskAnalysisContainer)
        
        # Load playbook rules relevant to the contract type to feed into risk analysis
        playbook = get_playbook()
        contract_type = state["contract_type"]
        playbook_guidelines = ""
        
        if contract_type in playbook.get("contract_types", {}):
            clauses_rules = playbook["contract_types"][contract_type].get("clauses", [])
            for r in clauses_rules:
                playbook_guidelines += f"- Clause Type: {r['clause_type']}\n"
                playbook_guidelines += f"  Guideline: {r['standard_guideline']}\n"
                playbook_guidelines += "  Risk Triggers:\n"
                for trigger in r.get("risk_triggers", []):
                    playbook_guidelines += f"    * {trigger}\n"
        
        # Prepare clauses input
        clauses_input = []
        for c in state["extracted_clauses"]:
            clauses_input.append({
                "clause_type": c.clause_type,
                "clause_text": c.clause_text
            })
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert legal risk auditor. Assess the risk level (Low, Medium, High) of each extracted clause. "
                       "Consider standard legal rules and the playbook guidelines provided. "
                       "Identify hidden traps, unfavorable conditions, or omissions. Provide detailed explanations and actionable mitigation recommendations."),
            ("user", "Assess the risks of these extracted clauses using the playbook guidelines.\n\n"
                     "Playbook Guidelines for {contract_type}:\n{playbook_guidelines}\n\n"
                     "Extracted Clauses:\n{clauses_json}")
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({
            "contract_type": state["contract_type"],
            "playbook_guidelines": playbook_guidelines or "Use standard legal risk practices.",
            "clauses_json": json.dumps(clauses_input, indent=2)
        })
        
        # Handle dict or Pydantic result object due to provider variations
        if isinstance(result, dict):
            risks_raw = result.get("risks", [])
            risk_analysis = []
            for r in risks_raw:
                if isinstance(r, dict):
                    risk_analysis.append(RiskAnalysis(**r))
                else:
                    risk_analysis.append(r)
        else:
            risk_analysis = result.risks

        return {
            "risk_analysis": risk_analysis,
            "current_step": "comparator",
            "error": None
        }
    except Exception as e:
        print(f"Risk Analyzer Agent error: {e}")
        return {
            "current_step": "end",
            "error": f"Risk Analyzer failed: {str(e)}"
        }

def comparator_node(state: GraphState) -> Dict[str, Any]:
    """Comparator Agent: Compares contract clauses with the legal playbook standard."""
    print("Executing Comparator Agent...")
    if state.get("error"):
        return state
        
    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(ComparisonContainer)
        
        playbook = get_playbook()
        contract_type = state["contract_type"]
        playbook_clauses = playbook.get("contract_types", {}).get(contract_type, {}).get("clauses", [])
        
        # Map playbook clauses for prompt
        playbook_guidelines = ""
        for pc in playbook_clauses:
            playbook_guidelines += f"- {pc['clause_type']}: {pc['standard_guideline']}\n"
            
        # Map extracted clauses
        extracted_info = ""
        for ec in state["extracted_clauses"]:
            extracted_info += f"- {ec.clause_type}: {ec.clause_text}\n"
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an elite legal contract comparison counsel. Compare the clauses extracted from the contract "
                       "against the playbook guidelines. Assess compliance status (Compliant, Partially Compliant, Non-Compliant), "
                       "detail all deviations, and propose structured renegotiation strategies. "
                       "Also determine the overall risk score (Low, Medium, High) and provide a concise 2-3 sentence executive summary."),
            ("user", "Compare the extracted contract clauses with the playbook rules.\n\n"
                     "Playbook Rules:\n{playbook_guidelines}\n\n"
                     "Extracted Clauses:\n{extracted_info}")
        ])
        
        chain = prompt | structured_llm
        result = chain.invoke({
            "playbook_guidelines": playbook_guidelines or "Compare against general best practices for this type of contract.",
            "extracted_info": extracted_info
        })
        
        # Handle dict or Pydantic result object due to provider variations
        if isinstance(result, dict):
            comparisons_raw = result.get("comparisons", [])
            comparison_results = []
            for c in comparisons_raw:
                if isinstance(c, dict):
                    comparison_results.append(ComparisonItem(**c))
                else:
                    comparison_results.append(c)
            overall_risk_score = result.get("overall_risk_score", "Medium")
            summary = result.get("summary", "Analysis completed.")
        else:
            comparison_results = result.comparisons
            overall_risk_score = result.overall_risk_score
            summary = result.summary

        return {
            "comparison_results": comparison_results,
            "overall_risk_score": overall_risk_score,
            "summary": summary,
            "current_step": "end",
            "error": None
        }
    except Exception as e:
        print(f"Comparator Agent error: {e}")
        return {
            "current_step": "end",
            "error": f"Comparator failed: {str(e)}"
        }

# ==========================================
# Compile State Graph
# ==========================================

def get_analysis_workflow():
    workflow = StateGraph(GraphState)
    
    # Add Nodes
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("risk_analyzer", risk_analyzer_node)
    workflow.add_node("comparator", comparator_node)
    
    # Set Entry Point and Edges
    workflow.set_entry_point("extractor")
    workflow.add_edge("extractor", "risk_analyzer")
    workflow.add_edge("risk_analyzer", "comparator")
    workflow.add_edge("comparator", END)
    
    return workflow.compile()

def run_agent_pipeline(contract_text: str, contract_type: str = "General") -> Dict[str, Any]:
    """Runs the full 3-agent pipeline on a contract."""
    compiled_app = get_analysis_workflow()
    
    initial_state: GraphState = {
        "contract_text": contract_text,
        "contract_type": contract_type,
        "extracted_clauses": [],
        "risk_analysis": [],
        "comparison_results": [],
        "current_step": "extractor",
        "overall_risk_score": None,
        "summary": None,
        "error": None
    }
    
    final_state = compiled_app.invoke(initial_state)
    return final_state
