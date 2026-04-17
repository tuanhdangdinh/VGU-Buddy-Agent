from langchain_core.tools import tool
from .rag import search_docs


@tool
def search_handbook(query: str) -> str:
    """Tìm kiếm thông tin trong sổ tay sinh viên VGU và tài liệu khóa học.
    Dùng khi cần thông tin về quy chế, chính sách, chương trình học, lịch học,
    học bổng, ký túc xá hoặc bất kỳ thủ tục hành chính nào của VGU.
    """
    results = search_docs(query)
    if not results:
        return "Không tìm thấy thông tin liên quan trong tài liệu."
    
    # Prefix context blocks to help the LLM recognize individual chunks
    return "\n\n---\n\n".join(results)
