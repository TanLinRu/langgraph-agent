import json
import os
from datetime import datetime

memory_dir = './memory'
os.makedirs(memory_dir, exist_ok=True)

agents_file = os.path.join(memory_dir, 'agents.json')
if os.path.exists(agents_file):
    with open(agents_file, 'r', encoding='utf-8') as f:
        agents = json.load(f)
else:
    agents = []

new_agents = [
    {
        'id': 'crm-agent',
        'name': 'CRM Agent',
        'description': '负责客户信息管理、跟进计划、CRM 操作',
        'llm_model': 'openai:gpt-4o',
        'system_prompt': '你是专业的 CRM 助手，负责客户信息管理和跟进。可以提取客户信息、生成跟进计划、管理客户关系。',
        'tools': ['Bash', 'Read', 'Edit', 'Glob', 'Grep'],
        'execution_mode': 'sync',
        'timeout': 120,
        'is_builtin': False,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    },
    {
        'id': 'data-analyst-agent',
        'name': 'Data Analyst Agent',
        'description': '负责数据分析、报表生成、统计查询',
        'llm_model': 'openai:gpt-4o',
        'system_prompt': '你是专业的数据分析师。擅长数据查询、统计分析、报表生成和可视化。',
        'tools': ['Bash', 'Read', 'Glob', 'Grep'],
        'execution_mode': 'sync',
        'timeout': 180,
        'is_builtin': False,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    },
    {
        'id': 'prd-designer-agent',
        'name': 'PRD Designer Agent',
        'description': '负责 PRD 可视化设计、流程图生成、HTML 原型输出',
        'llm_model': 'openai:gpt-4o',
        'system_prompt': '你是专业的 PRD 设计师。擅长需求分析、流程设计、HTML 原型生成。',
        'tools': ['Bash', 'Read', 'Edit', 'Glob', 'Grep'],
        'execution_mode': 'sync',
        'timeout': 180,
        'is_builtin': False,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    },
]

existing_ids = {a['id'] for a in agents}
for agent in new_agents:
    if agent['id'] not in existing_ids:
        agents.append(agent)
        print(f"Added: {agent['id']}")

with open(agents_file, 'w', encoding='utf-8') as f:
    json.dump(agents, f, indent=2, ensure_ascii=False)

print(f'Total agents: {len(agents)}')