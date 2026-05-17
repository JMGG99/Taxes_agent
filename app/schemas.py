from pydantic import BaseModel, Field


class TaxRecordResponse(BaseModel):
    filing_status: str
    income_from:   int = Field(description="Lower bound of the income bracket (inclusive), in dollars")
    income_to:     int = Field(description="Upper bound of the income bracket (exclusive), in dollars")
    amount:        int = Field(description="Federal income tax owed (negative value, in dollars)")

    model_config = {"from_attributes": True}


class EICCreditResponse(BaseModel):
    year:                int
    filing_status:       str
    income_from:         int  = Field(description="Lower bound of the income bracket (inclusive), in dollars")
    income_to:           int  = Field(description="Upper bound of the income bracket (exclusive), in dollars")
    amount:              int  = Field(description="EIC credit returned to the taxpayer (positive value, in dollars)")
    qualifying_children: int  = Field(description="Number of qualifying children (0–3)")

    model_config = {"from_attributes": True}


class WithholdingBracketResponse(BaseModel):
    year:               int
    filing_status:      str
    pay_period:         str
    income_from:        float = Field(description="Lower bound of the wage bracket (inclusive), in dollars")
    income_to:          float = Field(description="Upper bound of the wage bracket (exclusive), in dollars")
    withholding_amount: float = Field(description="Federal income tax the employer should withhold, in dollars")
    withholding_type:   str   = Field(description="standard = Step 2 box unchecked | checkbox = Step 2 box checked")

    model_config = {"from_attributes": True}
