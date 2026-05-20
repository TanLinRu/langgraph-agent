import logging
from src.agent.context.long_term import LongTermManager
from src.agent.context.compression import ContextCompressor


logger = logging.getLogger(__name__)


class MemoryManager:
    """分层记忆系统，统一 L1-L4 接口。

    全部为同步接口，兼容 LangGraph hook 的执行模型。
    """

    def __init__(self, long_term: LongTermManager, compressor: ContextCompressor):
        self._lt = long_term
        self._compressor = compressor

    def retrieve(self, user_id: str, thread_id: str, top_k: int = 3) -> list:
        contexts = []
        try:
            query = f"{user_id} {thread_id}"
            docs = self._lt.search_similar(query=query, top_k=top_k)
            if docs:
                contexts.extend(list(docs))
        except Exception:
            logger.warning("[MemoryManager] Memory retrieval failed", exc_info=True)
        return contexts

    def store_session(self, thread_id: str, messages: list):
        try:
            self._lt.save_session(thread_id, messages, metadata={})
        except Exception:
            logger.warning("[MemoryManager] Session store failed", exc_info=True)

    def compress(self, messages: list, token_usage: dict, compression_count: int):
        percentage = token_usage.get("percentage", 0)
        if percentage < 70 or compression_count >= 5:
            return None, compression_count
        try:
            result = self._compressor.compress(messages)
            if result and result.compressed_messages:
                return result.compressed_messages, compression_count + 1
        except Exception:
            logger.warning("[MemoryManager] Compression failed", exc_info=True)
        return None, compression_count
