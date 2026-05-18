from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.agent import run_agent
from app.limiter import limiter

router = APIRouter()


class AgentRequest(BaseModel):
    question: str


class AgentResponse(BaseModel):
    answer: str


@router.post("/agent", response_model=AgentResponse, summary="Ask the tax assistant a question")
@limiter.limit("20/minute")
async def ask_agent(request: Request, body: AgentRequest):
    try:
        answer = await run_agent(body.question)
        return AgentResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
