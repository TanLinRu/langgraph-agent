# TASK: PC Automation/Simulation Capabilities Research

## Task Overview

Research and plan the integration of local PC automation/simulation capabilities into the LangGraph agent architecture. This will enable the AI agent to control desktop applications, perform GUI automation, and interact with the local computer environment beyond file operations.

## Current Status

### Research Completed
- Web search conducted on existing frameworks and solutions
- Analysis of AI agent desktop automation patterns (Claude Computer Use, Open Interpreter, Browser Use, etc.)
- Security and sandboxing considerations researched
- Human-in-loop patterns analyzed
- Current codebase architecture reviewed (tools/__init__.py, graph.py, agent.py, human_in_loop.py)

### Current Tool Capabilities
The agent currently has these tools (in `src/agent/tools/__init__.py`):
- `execute_code` - Execute Python code
- `read_file` / `write_file` / `list_directory` / `search_files` - File operations
- `data_processor` - CSV/JSON processing
- `dispatch_to_cli` / `dispatch_via_acp` - External CLI dispatch
- `list_clis` / `list_serves` / `stop_serve_tool` - Service management

### Existing HITL System
The agent has a basic human-in-loop system in `src/agent/human_in_loop.py`:
- Approval types: TOOL_EXECUTION, WRITE_OPERATION, WORKFLOW_STEP, CODE_EXECUTION, RESOURCE_ACCESS
- Supports async approval requests with timeout
- Callback mechanism for notifications

## Research Summary

### 1. Existing Solutions

| Framework | Type | Platform | Key Strengths | Limitations |
|-----------|------|----------|---------------|-------------|
| **PyAutoGUI** | Low-level mouse/keyboard | Cross-platform | Simple API, image recognition | Brittle, coordinate-based |
| **pywinauto** | Control-based | Windows only | UIA accessibility, stable | Windows-only |
| **Playwright** | Browser automation | Cross-platform | Modern, reliable, MCP support | Browser only |
| **Selenium** | Browser automation | Cross-platform | Mature, wide support | Browser only |
| **Robot Framework** | RPA/Test framework | Cross-platform | Keyword-driven, extensible | Heavy, complex setup |
| **AutoIt** | Scripting language | Windows only | Lightweight, powerful | No LLM integration |
| **Windows-Use** | AI + UIA | Windows only | UIA + LLM, semantic UI | Relatively new |
| **Claude Computer Use** | Vision-based | Cross-platform | General-purpose GUI control | Expensive per-action |

### 2. AI Agent Patterns

**Claude Computer Use (Anthropic)**:
- Screenshot-based vision approach
- Mouse clicks, keyboard input, scroll actions
- Docker sandboxed execution
- Human-in-loop for sensitive operations

**Open Interpreter**:
- Hybrid approach: GUI control + code execution
- Computer use with OS-level primitives
- Permission-based access control

**Browser Use** (open source):
- DOM + LLM for web automation
- 81k GitHub stars, 89.1% WebVoyager benchmark
- ~$0.07 per 10-step task

**Playwright MCP** (Microsoft):
- Accessibility tree-based automation
- Sub-100ms actions
- Free, MCP-compatible
- In GitHub Copilot Agent

**Fazm (macOS)**:
- Accessibility API-based automation
- Real logged-in browser via Chrome extension
- Cross-app workflows

### 3. Security Considerations

**Sandbox Approaches**:
1. **OS-native sandboxing** (Cursor approach)
   - macOS: Seatbelt via sandbox-exec
   - Linux: Landlock + seccomp
   - Windows: WSL2 for Linux sandbox
   - Most practical for local execution

2. **Container-based sandboxing** (Anthropic approach)
   - Docker container with Xvfb
   - Virtual display for headless operation
   - Strong isolation but latency overhead

3. **Virtual machine isolation**
   - Full VM per session
   - Maximum isolation
   - High resource overhead

**Permission Tiers** (recommended):
- **Basic**: Read-only operations, screenshot only
- **Standard**: Mouse/keyboard control within approved apps
- **Elevated**: File writes outside workspace, system commands
- **Critical**: Financial transactions, credential access, system changes

**Human-in-Loop Integration Points**:
- Authentication actions (login, password entry)
- Financial transactions (purchases, payments)
- File operations on sensitive paths
- System configuration changes
- Download and execution of files

## Recommended Architecture

```
                    LangGraph Agent
                     (Think -> Execute -> Compress -> Save)
                             |
                    Tool Execution Layer
                             |
         +-------------------+-------------------+
         |                   |                   |
   Sandbox Layer     Permission Tier       HITL Gate
         |                   |                   |
         +-------------------+-------------------+
                             |
         +-------------------+-------------------+
         |                   |                   |
   Vision Engine      Accessibility       Browser
   (Screenshot +        Engine           Automation
    Vision Model)    (pywinauto UIA)    (Playwright MCP)
```

## New Tools Needed

| Tool | Purpose | Permission Level |
|------|---------|-------------------|
| `take_screenshot` | Capture current screen | Basic |
| `analyze_screen` | Send screenshot to vision model | Basic |
| `mouse_click` | Click at coordinates or element | Standard |
| `mouse_move` | Move cursor | Standard |
| `keyboard_type` | Type text | Standard |
| `keyboard_press` | Press keys/combinations | Standard |
| `scroll` | Scroll action | Standard |
| `get_window_info` | Get window handles and positions | Standard |
| `launch_app` | Start a desktop application | Elevated |
| `close_app` | Close an application | Elevated |
| `browser_navigate` | Navigate browser URL | Standard |
| `browser_snapshot` | Get browser accessibility tree | Standard |

## Implementation Plan

### Phase 1: Core Infrastructure (2-3 days)
1. Add `AGENT_PC_AUTOMATION_ENABLED` config option
2. Add `AGENT_SANDBOX_MODE` (none, os-native, container)
3. Create `sandbox/` module
4. Create `automation/` module

### Phase 2: Basic Tools (3-4 days)
1. Implement `take_screenshot` tool
2. Implement `mouse_control` tool
3. Implement `keyboard_control` tool
4. Implement `window_control` tool
5. Add permission tier checking

### Phase 3: Advanced Tools (3-4 days)
1. Implement `playwright_control` tool via MCP
2. Implement `desktop_app_control` tool via pywinauto
3. Implement `screenshot_analyze` tool with vision model

### Phase 4: Safety & Integration (2-3 days)
1. Extend HITL for GUI approval flow
2. Add audit logging
3. Implement emergency stop mechanism

**Total Estimated: 10-14 days**

## Open Questions

1. Should the agent support cross-platform (Windows + macOS + Linux) or Windows-first?
2. Is the vision-based approach preferred over accessibility API approach?
3. Should browser automation be integrated via existing MCP protocol or custom tools?
4. What is the acceptable latency for GUI actions?
5. Should the agent work on the user'"'"'s real desktop or a sandboxed virtual desktop?
