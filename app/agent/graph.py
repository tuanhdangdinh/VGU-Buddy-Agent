"""
Agentic RAG with LangGraph — Study Buddy for VGU students.

Graph flow (per docs.langchain.com/oss/python/langgraph/agentic-rag):
  START
    → generate_query_or_respond   (LLM decides: call tool or answer directly)
        → [tool call]  → retrieve (ToolNode)
            → grade_documents     (relevant? → generate_answer / rewrite_question)
                → generate_answer → END
                → rewrite_question → generate_query_or_respond  (retry loop)
        → [no tool call] → END
"""
import logging
from typing import Literal, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from ..config import settings
from .tools import search_handbook

logger = logging.getLogger(__name__)

# Used in generate_query_or_respond — instructs the LLM to call the tool
RETRIEVAL_PROMPT = """You are Study Buddy — AI learning assistant for VGU students.

CRITICAL: The handbook is written in ENGLISH. Always translate Vietnamese queries to English before calling search_handbook.

Rules:
1. ALWAYS call search_handbook with an ENGLISH query.
2. For list/count questions, call search_handbook at least 2 times with different English queries.
3. Never ask the user for clarification — search first."""

# Used in generate_answer — instructs the LLM to synthesize, NOT call tools
ANSWER_PROMPT = """Bạn là Study Buddy — trợ lý học tập AI cho sinh viên VGU (Đại học Việt-Đức).
Nhiệm vụ: tổng hợp thông tin đã tìm được và trả lời câu hỏi. KHÔNG tìm kiếm thêm.

Quy tắc trả lời:
- Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng.
- BẮT BUỘC chỉ tóm tắt thông tin được cung cấp từ tài liệu (information from student handbook/context), không bịaa đặt (no hallucination).
- Luôn luôn trích dẫn nguồn khi nêu thông tin, ví dụ: "Theo [Source: Tên tài liệu], ..." hoặc "(Nguồn: Tên tài liệu)". Dữ liệu được cung cấp sẽ có đoạn "[Source: ...]" ở đầu mỗi mục.
- Nếu câu hỏi hỏi "bao nhiêu / mấy": ĐẾM số lượng item tìm được rồi nêu rõ con số (VD: "Có 3 môn toán:").
- Liệt kê đầy đủ mã môn (VD: 61CSE107) và tên môn khi hỏi về danh sách.
- Nếu tìm thấy thông tin giảng viên (Lecturer / Module coordinator): nêu rõ tên người dạy.
- Chỉ nói "không tìm thấy" nếu thông tin được cung cấp HOÀN TOÀN không đề cập đến chủ đề."""


def _get_llm() -> ChatGoogleGenerativeAI:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.1,
        max_output_tokens=1024,
    )


# ─── Nodes ───────────────────────────────────────────────────

def generate_query_or_respond(state: MessagesState):
    """LLM decides: call search_handbook tool or answer directly."""
    llm = _get_llm()
    messages = [SystemMessage(content=RETRIEVAL_PROMPT)] + state["messages"]
    response = llm.bind_tools([search_handbook]).invoke(messages)
    return {"messages": [response]}


def grade_documents(state: MessagesState) -> Literal["generate_answer", "rewrite_question"]:
    """
    Conditional edge after retrieve:
    - If docs are relevant → generate_answer
    - If docs are empty/irrelevant → rewrite_question (max 1 retry)
    """
    messages = state["messages"]

    # Limit rewrites to 1 attempt to avoid infinite loops
    human_count = sum(1 for m in messages if isinstance(m, HumanMessage))
    if human_count >= 2:
        logger.info("grade_documents: max rewrites reached → generate_answer")
        return "generate_answer"

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            if msg.content and "Không tìm thấy" not in msg.content:
                logger.info("grade_documents: relevant docs found → generate_answer")
                return "generate_answer"
            break

    logger.info("grade_documents: no relevant docs → rewrite_question")
    return "rewrite_question"


def rewrite_question(state: MessagesState):
    """
    Translate/rephrase the question into English for better retrieval
    from the English-language handbook.
    """
    messages = state["messages"]
    original = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=(
            "Translate and rephrase into a concise English search query "
            "for a university module handbook. Return ONLY the query."
        )),
        HumanMessage(content=original),
    ])
    logger.info(f"rewrite_question: '{original[:60]}' → '{response.content[:60]}'")
    # Append rewritten query — MessagesState reducer adds to list
    return {"messages": [HumanMessage(content=response.content)]}


def generate_answer(state: MessagesState):
    """
    Generate final answer by extracting question + context explicitly.
    Avoids passing raw tool_call messages to Gemini which causes re-invocation.
    """
    messages = state["messages"]

    # Original question (last HumanMessage = current question)
    original_q = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )

    # All retrieved context from ToolMessages
    contexts = [m.content for m in messages if isinstance(m, ToolMessage) and m.content]
    context_text = "\n\n---\n\n".join(contexts) if contexts else "Không có thông tin từ tài liệu."

    llm = _get_llm()  # no bind_tools — prevent re-invocation
    response = llm.invoke([
        SystemMessage(content=ANSWER_PROMPT),
        HumanMessage(content=(
            f"Câu hỏi: {original_q}\n\n"
            f"Thông tin tìm được từ sổ tay sinh viên:\n{context_text}\n\n"
            "Dựa vào thông tin trên, hãy trả lời câu hỏi một cách ngắn gọn và chính xác."
        )),
    ])
    return {"messages": [response]}


# ─── Graph ───────────────────────────────────────────────────

def _build_graph():
    workflow = StateGraph(MessagesState)

    workflow.add_node("generate_query_or_respond", generate_query_or_respond)
    workflow.add_node("retrieve", ToolNode([search_handbook]))
    workflow.add_node("rewrite_question", rewrite_question)
    workflow.add_node("generate_answer", generate_answer)

    workflow.add_edge(START, "generate_query_or_respond")
    workflow.add_conditional_edges(
        "generate_query_or_respond",
        tools_condition,
        {"tools": "retrieve", END: END},
    )
    workflow.add_conditional_edges("retrieve", grade_documents)
    workflow.add_edge("generate_answer", END)
    workflow.add_edge("rewrite_question", "generate_query_or_respond")

    return workflow.compile()


_agent_graph = None


def get_agent():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = _build_graph()
        logger.info(f"Agentic RAG graph ready — model={settings.llm_model}")
    return _agent_graph


async def run_agent(question: str, history: list) -> Tuple[str, int, int]:
    """Returns (answer, input_tokens, output_tokens)."""
    agent = get_agent()

    # Pass history as SystemMessage — keeps graph messages to a single
    # HumanMessage so grade_documents rewrite counter and question
    # extraction work correctly on the current question only.
    messages = []
    if history:
        history_lines = []
        for msg in history[-12:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_lines.append(f"{role}: {msg['content']}")
        messages.append(SystemMessage(content=(
            "Previous conversation context (for reference only):\n"
            + "\n".join(history_lines)
        )))
    messages.append(HumanMessage(content=question))

    result = await agent.ainvoke({"messages": messages})
    last = result["messages"][-1]

    answer = last.content if isinstance(last.content, str) else str(last.content)
    usage = getattr(last, "usage_metadata", None) or {}
    input_tokens = usage.get("input_tokens", max(len(question.split()) * 2, 50))
    output_tokens = usage.get("output_tokens", max(len(answer.split()) * 2, 50))

    return answer, input_tokens, output_tokens
