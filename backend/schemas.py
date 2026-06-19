from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class ExtractedClause(BaseModel):
    clause_type: str = Field(description="The category of the clause (e.g., Confidentiality, Indemnification, Governing Law, Liability Cap, Termination).")
    clause_text: str = Field(description="The exact text of the clause extracted from the document.")
    confidence_score: float = Field(description="Confidence score between 0.0 and 1.0 of the extraction accuracy.")
    page_number: Optional[int] = Field(default=None, description="The page number where the clause is found.")
    line_number: Optional[int] = Field(default=None, description="The line number or section identifier if applicable.")

class RiskAnalysis(BaseModel):
    clause_type: str = Field(description="The category of the clause being analyzed.")
    risk_level: str = Field(description="Risk level evaluation: 'Low', 'Medium', or 'High'.")
    risk_description: str = Field(description="Detailed explanation of the risk found in the clause.")
    mitigation_suggestion: str = Field(description="Actionable advice on how to rewrite or negotiate this clause to reduce risk.")

class ComparisonItem(BaseModel):
    clause_type: str = Field(description="The type of clause compared.")
    extracted_text: str = Field(description="The text found in the contract.")
    standard_guideline: str = Field(description="The standard playbook guideline for this clause.")
    compliance_status: str = Field(description="Status: 'Compliant', 'Partially Compliant', or 'Non-Compliant'.")
    deviation_details: str = Field(description="Specific ways the extracted clause deviates from the playbook standard.")
    renegotiation_strategy: str = Field(description="Strategy for aligning the clause with playbook standards.")

class AgentState(BaseModel):
    contract_text: str = Field(description="The raw text of the contract to analyze.")
    contract_type: str = Field(description="The identified type of contract (e.g., NDA, SaaS Agreement, Employment Agreement).")
    extracted_clauses: List[ExtractedClause] = Field(default=[], description="List of clauses extracted by the Extractor agent.")
    risk_analysis: List[RiskAnalysis] = Field(default=[], description="List of risks analyzed by the Risk Analyzer agent.")
    comparison_results: List[ComparisonItem] = Field(default=[], description="List of clause comparisons analyzed by the Comparator agent.")
    current_step: str = Field(default="init", description="Current step in the LangGraph workflow.")
    error: Optional[str] = Field(default=None, description="Error message if the pipeline failed at any step.")

class AnalysisResponse(BaseModel):
    document_id: str
    filename: str
    contract_type: str
    extracted_clauses: List[ExtractedClause]
    risk_analysis: List[RiskAnalysis]
    comparison_results: List[ComparisonItem]
    overall_risk_score: str # 'Low', 'Medium', 'High'
    summary: str

class SearchResultItem(BaseModel):
    document_id: str
    filename: str
    clause_type: str
    text: str
    score: float
    page_number: Optional[int]
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]

class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    contract_type: str
    upload_time: str
    size_bytes: int

class PlaybookClauseSchema(BaseModel):
    clause_type: str
    description: str
    standard_guideline: str
    risk_triggers: List[str]

class PlaybookContractSchema(BaseModel):
    name: str
    clauses: List[PlaybookClauseSchema]

class PlaybookSchema(BaseModel):
    contract_types: Dict[str, PlaybookContractSchema]
