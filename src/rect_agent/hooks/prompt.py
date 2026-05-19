import logging
from typing import Any

from langchain_core.messages import SystemMessage

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.skills import SKILLS_INDEX
from src.agent.context.long_term import LongTermManager

logger = logging.getLogger(__name__)


def build_prompt_fn(long_term: LongTermManager | None = None):
    def prompt_fn(state: dict) -> list:
        messages = list(state.get("messages", []))
        has_system = any(getattr(m, "type", None) == "system" for m in messages)

        if not has_system:
            system_blocks = [SYSTEM_PROMPT]

            if SKILLS_INDEX:
                system_blocks.append(f"\n## 可用技能\n{SKILLS_INDEX}")

            user_id = state.get("user_id", "default")
            thread_id = state.get("thread_id", "default")
            tenant_id = state.get("tenant_id", "")
            org_id = state.get("org_id", "")

            if long_term and user_id:
                try:
                    profile = long_term.load_user_profile(user_id, tenant_id, org_id)
                    if profile and hasattr(profile, "to_system_block"):
                        profile_block = profile.to_system_block()
                        if profile_block:
                            system_blocks.append(profile_block)
                except Exception:
                    logger.warning("[Prompt] Failed to load user profile", exc_info=True)

            sop_name = state.get("sop_name")
            if sop_name and long_term:
                try:
                    sop_state = long_term.load_sop_state(sop_name, thread_id)
                    if sop_state:
                        system_blocks.append(f"\n## 当前工作流进度\n{sop_state}")
                except Exception:
                    logger.warning(f"[Prompt] Failed to load SOP {sop_name}", exc_info=True)

            system_text = "\n\n".join(system_blocks)
            messages.insert(0, SystemMessage(content=system_text))

        return messages

    return prompt_fn
