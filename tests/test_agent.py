import asyncio
from app.agent import run_agent
from app.agent_tools import setup_loop


async def main():
    setup_loop(asyncio.get_running_loop())

    question = "How much federal income tax does a single filer owe with a taxable income of $45,000 in 2025?"
    print(f"Question: {question}\n")

    answer = await run_agent(question)
    print(f"Answer:\n{answer}")


if __name__ == "__main__":
    asyncio.run(main())
