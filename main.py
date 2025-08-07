#!/usr/bin/env python3
"""
Simple Browser Automation Agent
Inspired by nanoGPT's simplicity and Browser-Use/Notte's effectiveness
"""

import asyncio
import json
import os
import sys
import time
import requests
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

# Third-party imports
from patchright.async_api import async_playwright, Page, Browser, BrowserContext
from pydantic import BaseModel, Field
import ollama

from loguru import logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# Configuration Section (nanoGPT style)
# ============================================================================

# LLM configuration
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-oss:20b")  # qwen3:32b, gpt-oss:20b, or gpt-oss:120b
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Browser configuration
HEADLESS = False  # Set to True for production
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800
USER_AGENT = None  # Use default

# DOM extraction configuration
MAX_ELEMENTS = 100  # Maximum interactive elements to extract
INCLUDE_ATTRIBUTES = ["id", "class", "href", "title", "alt", "placeholder", "value", "type"]

# Agent configuration
MAX_STEPS = 30
TIMEOUT_MS = 30000  # 30 seconds
RETRY_ATTEMPTS = 3
THINK_TIME = 0.5  # Seconds to wait between actions

# Logging configuration
LOG_LEVEL = "DEBUG"
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)

# ============================================================================
# Data Models
# ============================================================================

class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    WAIT = "wait"
    EXTRACT = "extract"
    DONE = "done"

@dataclass
class DOMElement:
    """Represents an interactive DOM element"""
    index: int
    tag: str
    text: str
    attributes: Dict[str, str]
    xpath: str
    is_visible: bool = True
    is_clickable: bool = False
    is_input: bool = False

    def to_string(self) -> str:
        """Convert to LLM-friendly string representation"""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        element_type = "input" if self.is_input else "button" if self.is_clickable else self.tag
        return f"[{self.index}] {element_type}: {text_preview}"

@dataclass
class BrowserState:
    """Current state of the browser"""
    url: str
    title: str
    elements: List[DOMElement]
    screenshot: Optional[bytes] = None
    
    def to_prompt_string(self) -> str:
        """Convert state to prompt-friendly format"""
        elements_str = "\n".join([e.to_string() for e in self.elements[:50]])  # Limit elements
        return f"""Current Page:
URL: {self.url}
Title: {self.title}

Interactive Elements:
{elements_str}
"""

class AgentAction(BaseModel):
    """Action to be performed by the agent"""
    reasoning: str = Field(description="Step-by-step reasoning for this action")
    action: ActionType = Field(description="Type of action to perform")
    element_index: Optional[int] = Field(None, description="Index of element to interact with")
    value: Optional[str] = Field(None, description="Value for type actions or extraction result")

# ============================================================================
# Browser Controller
# ============================================================================

class BrowserController:
    """Handles browser automation using patchright"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.element_map: Dict[int, DOMElement] = {}
    
    async def start(self):
        """Launch browser and create page"""
        logger.info("Starting browser...")
        self.playwright = await async_playwright().start()
        
        # Use patchright's anti-detection features
        self.browser = await self.playwright.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            user_agent=USER_AGENT
        )
        
        self.page = await self.context.new_page()
        logger.info("Browser started successfully")
    
    async def close(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
        logger.info("Browser closed")
    
    async def navigate(self, url: str) -> bool:
        """Navigate to URL"""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            await self.page.wait_for_load_state("networkidle", timeout=5000)
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False
    
    async def extract_dom(self) -> List[DOMElement]:
        """Extract interactive elements from DOM using JavaScript"""
        
        # JavaScript to extract interactive elements
        js_code = """
        () => {
            const elements = [];
            let index = 1;
            
            // Find all potentially interactive elements
            const selectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [onclick]';
            const allElements = document.querySelectorAll(selectors);
            
            for (const el of allElements) {
                // Skip invisible elements
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    continue;
                }
                
                // Get element info
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                
                // Generate XPath
                function getXPath(element) {
                    if (element.id) return `//*[@id="${element.id}"]`;
                    if (element === document.body) return '/html/body';
                    
                    let ix = 0;
                    const siblings = element.parentNode.childNodes;
                    for (let i = 0; i < siblings.length; i++) {
                        const sibling = siblings[i];
                        if (sibling === element) {
                            return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                        }
                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                            ix++;
                        }
                    }
                }
                
                elements.push({
                    index: index++,
                    tag: el.tagName.toLowerCase(),
                    text: el.innerText || el.value || el.placeholder || '',
                    attributes: {
                        id: el.id || '',
                        class: el.className || '',
                        href: el.href || '',
                        type: el.type || '',
                        placeholder: el.placeholder || '',
                        value: el.value || ''
                    },
                    xpath: getXPath(el),
                    is_visible: true,
                    is_clickable: el.tagName === 'BUTTON' || el.tagName === 'A' || el.role === 'button' || (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button')),
                    is_input: (el.tagName === 'INPUT' && el.type !== 'submit' && el.type !== 'button' && el.type !== 'reset') || el.tagName === 'TEXTAREA'
                });
                
                if (elements.length >= """ + str(MAX_ELEMENTS) + """) break;
            }
            
            return elements;
        }
        """
        
        try:
            elements_data = await self.page.evaluate(js_code)
            elements = []
            self.element_map = {}
            
            for elem_data in elements_data:
                element = DOMElement(
                    index=elem_data['index'],
                    tag=elem_data['tag'],
                    text=elem_data['text'],
                    attributes=elem_data['attributes'],
                    xpath=elem_data['xpath'],
                    is_visible=elem_data['is_visible'],
                    is_clickable=elem_data['is_clickable'],
                    is_input=elem_data['is_input']
                )
                elements.append(element)
                self.element_map[element.index] = element
            

            return elements
            
        except Exception as e:
            logger.error(f"DOM extraction failed: {e}")
            return []
    
    async def get_state(self) -> BrowserState:
        """Get current browser state"""
        url = self.page.url
        title = await self.page.title()
        elements = await self.extract_dom()
        
        # Optionally capture screenshot
        screenshot = None
        # screenshot = await self.page.screenshot()
        
        return BrowserState(url=url, title=title, elements=elements, screenshot=screenshot)
    
    async def click_element(self, index: int) -> bool:
        """Click element by index"""
        if index not in self.element_map:
            logger.error(f"Element {index} not found")
            return False
        
        element = self.element_map[index]
        try:
            # Try to click using XPath
            await self.page.click(f'xpath={element.xpath}', timeout=5000)
            await asyncio.sleep(THINK_TIME)
            return True
        except Exception as e:
            logger.error(f"Click failed: {e}")
            # Fallback: try JavaScript click
            try:
                await self.page.evaluate(f"""
                    document.evaluate('{element.xpath}', document, null, 
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click()
                """)
                return True
            except Exception as e:
                logger.error(f"Fallback click failed: {e}")
                return False
    
    async def type_text(self, index: int, text: str) -> bool:
        """Type text into element"""
        if index not in self.element_map:
            logger.error(f"Element {index} not found")
            return False
        
        element = self.element_map[index]
        try:
            # Clear existing text and type new
            await self.page.fill(f'xpath={element.xpath}', text)
            await asyncio.sleep(THINK_TIME)
            return True
        except Exception as e:
            logger.error(f"Type failed: {e}")
            return False
    
    async def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        """Scroll the page"""
        try:
            if direction == "down":
                await self.page.evaluate(f"window.scrollBy(0, {amount})")
            else:
                await self.page.evaluate(f"window.scrollBy(0, -{amount})")
            await asyncio.sleep(THINK_TIME)
            return True
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return False
    
    async def extract_text(self) -> str:
        """Extract all visible text from page"""
        try:
            text = await self.page.evaluate("""
                () => document.body.innerText || document.body.textContent || ''
            """)
            return text
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return ""

# ============================================================================
# LLM Reasoner
# ============================================================================

class LLMReasoner:
    """Handles LLM interactions using ollama"""
    
    def __init__(self, model: str = MODEL_NAME):
        self.client = ollama.Client(host=OLLAMA_HOST)
        self.model = model
    
    def create_system_prompt(self) -> str:
        """Create system prompt for the agent"""
        return """You are a browser automation agent. Your job is to complete web tasks by interacting with web pages.

You can perform these actions:
- navigate: Go to a URL
- click: Click on an element (specify element_index)
- type: Type text into an input field (specify element_index and value)
- scroll: Scroll the page up or down
- extract: Extract information from the page
- wait: Wait for page to load
- done: Task is complete

Always think step-by-step about what you need to do next. Be specific and precise.

IMPORTANT: Output exactly ONE action per response. Do not output multiple actions or JSON objects.

Output your response as a single JSON object with these fields:
{
    "reasoning": "Your step-by-step thinking about what to do next",
    "action": "navigate|click|type|scroll|extract|wait|done",
    "element_index": null or element number,
    "value": null or text to type/extract
}"""
    
    async def decide_action(self, task: str, state: BrowserState, history: List[str]) -> AgentAction:
        """Decide next action based on current state"""
        
        # Build context
        history_str = "\n".join(history[-5:]) if history else "No previous actions"
        
        prompt = f"""Task: {task}

{state.to_prompt_string()}

Previous Actions:
{history_str}

What should I do next? Respond with JSON."""
        
        try:
            # Call ollama with streaming
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.create_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "stream": True,
                "options": {"temperature": 0.7}
            }
            
            full_response = ""
            
            # Stream and output tokens
            r = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, stream=True, timeout=120)
            for line in r.iter_lines():
                if line:
                    data = json.loads(line.decode())
                    
                    if 'message' in data:
                        message = data['message']
                        content = message.get('content', '')
                        thinking_content = message.get('thinking', '')
                        
                        # Output thinking tokens
                        if thinking_content:
                            print(thinking_content, end='', flush=True)
                        
                        # Output response tokens
                        if content:
                            full_response += content
                            print(content, end='', flush=True)
            
            print()  # Add newline after streaming completes
            
            if not full_response.strip():
                raise ValueError("Empty response from Ollama")
            
            # Clean and parse the complete response
            clean_response = full_response.strip()
            
            # Try to extract JSON from the response if it's wrapped in other text
            json_start = clean_response.find('{')
            json_end = clean_response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                clean_response = clean_response[json_start:json_end]
            
            # Parse the complete response
            result = json.loads(clean_response)
            
            # Normalize action to lowercase if it exists
            if 'action' in result:
                result['action'] = result['action'].lower()
            
            action = AgentAction(**result)
            return action
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"Raw response: {repr(full_response[:1000])}")
            logger.error(f"Cleaned response: {repr(clean_response[:1000])}")
            # Fallback action
            return AgentAction(
                reasoning="JSON parsing error, waiting",
                action=ActionType.WAIT
            )
        except Exception as e:
            logger.error(f"LLM decision failed: {e}")
            logger.error(f"Response received: {repr(full_response[:1000])}")
            # Fallback action
            return AgentAction(
                reasoning="Error in LLM response, waiting",
                action=ActionType.WAIT
            )

# ============================================================================
# Main Agent
# ============================================================================

class BrowserAgent:
    """Main browser automation agent"""
    
    def __init__(self, task: str):
        self.task = task
        self.browser = BrowserController()
        self.llm = LLMReasoner()
        self.history: List[str] = []
        self.step_count = 0
    
    async def run(self, start_url: Optional[str] = None) -> Dict[str, Any]:
        """Run the agent to complete the task"""
        
        logger.info(f"Starting task: {self.task}")
        
        # Start browser
        await self.browser.start()
        
        # Navigate to start URL if provided
        if start_url:
            await self.browser.navigate(start_url)
        else:
            # Default to Google
            await self.browser.navigate("https://www.google.com")
        
        result = {
            "success": False,
            "steps": 0,
            "history": [],
            "final_url": "",
            "extracted_data": None
        }
        
        try:
            # Main agent loop
            while self.step_count < MAX_STEPS:
                self.step_count += 1
                logger.info(f"\n=== Step {self.step_count} ===")
                
                # Get current state
                state = await self.browser.get_state()
                
                # Decide action
                action = await self.llm.decide_action(self.task, state, self.history)
                
                # Execute action
                success = await self.execute_action(action, state)
                
                # Record history
                history_entry = f"Step {self.step_count}: {action.action}"
                if action.element_index:
                    history_entry += f" on element [{action.element_index}]"
                if action.value:
                    history_entry += f" with value: {action.value[:50]}"
                history_entry += f" - {'Success' if success else 'Failed'}"
                self.history.append(history_entry)
                
                # Check if done
                if action.action == ActionType.DONE:
                    logger.info("Task completed!")
                    result["success"] = True
                    result["extracted_data"] = action.value
                    break
                
                # Wait between actions
                await asyncio.sleep(THINK_TIME)
            
            # Prepare result
            result["steps"] = self.step_count
            result["history"] = self.history
            result["final_url"] = self.browser.page.url if self.browser.page else ""
            
        except Exception as e:
            logger.error(f"Agent error: {e}")
            result["error"] = str(e)
        
        finally:
            # Always close browser
            await self.browser.close()
        
        return result
    
    async def execute_action(self, action: AgentAction, _: BrowserState) -> bool:
        """Execute the decided action"""
        
        try:
            if action.action == ActionType.NAVIGATE:
                if action.value:
                    return await self.browser.navigate(action.value)
                return False
            
            elif action.action == ActionType.CLICK:
                if action.element_index:
                    return await self.browser.click_element(action.element_index)
                return False
            
            elif action.action == ActionType.TYPE:
                if action.element_index and action.value:
                    return await self.browser.type_text(action.element_index, action.value)
                return False
            
            elif action.action == ActionType.SCROLL:
                direction = action.value if action.value in ["up", "down"] else "down"
                return await self.browser.scroll(direction)
            
            elif action.action == ActionType.EXTRACT:
                text = await self.browser.extract_text()
                action.value = text[:1000]  # Limit extracted text
                return True
            
            elif action.action == ActionType.WAIT:
                await asyncio.sleep(2)
                return True
            
            elif action.action == ActionType.DONE:
                return True
            
            else:
                logger.warning(f"Unknown action: {action.action}")
                return False
                
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False

# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Example usage"""
    
    # Example tasks
    tasks = [
        ("Search for 'WebVoyager benchmark' on Google", "https://www.google.com"),
        # ("Find Python documentation", "https://www.python.org"),
        # ("Search for flights from NYC to SF", "https://www.google.com/travel/flights"),
    ]
    
    for task_description, start_url in tasks:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running task: {task_description}")
        logger.info(f"{'='*60}")
        
        agent = BrowserAgent(task=task_description)
        result = await agent.run(start_url=start_url)
        
        # Print resultsX``
        logger.info("\n=== Results ===")
        logger.info(f"Success: {result['success']}")
        logger.info(f"Steps taken: {result['steps']}")
        logger.info(f"Final URL: {result['final_url']}")
        
        if result.get('extracted_data'):
            logger.info(f"Extracted: {result['extracted_data'][:200]}...")
        
        # Save results
        output_file = Path(f"results_{int(time.time())}.json")
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        logger.info(f"Results saved to {output_file}")

if __name__ == "__main__":
    # Check if ollama is available
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        models = client.list()
        
        # Check if our model is available
        model_names = [m.model for m in models.models]
        if not any(MODEL_NAME in name for name in model_names):
            logger.warning(f"Model {MODEL_NAME} not found. Please run: ollama pull {MODEL_NAME}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Cannot connect to ollama: {e}")
        logger.error("Please ensure ollama is running: ollama serve")
        sys.exit(1)
    
    # Run the agent
    asyncio.run(main())