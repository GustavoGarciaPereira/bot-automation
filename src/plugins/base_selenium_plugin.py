"""Shared Selenium helpers for portal plugins.

Provides:
- ``selenium_manager`` context-manager that yields a configured WebDriver.
- Common wait strategies (element clickable, present, visible).
- Screenshot-on-failure decorator.
- Retry with exponential backoff via ``tenacity``.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Retryable exceptions for transient failures
# ---------------------------------------------------------------------------

RETRYABLE = (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    WebDriverException,  # covers many network-level issues
)

# ---------------------------------------------------------------------------
# Driver factory
# ---------------------------------------------------------------------------


def _build_chrome_options(headless: bool) -> ChromeOptions:
    opts = ChromeOptions()

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")

    # Common flags
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--window-size=1366,768")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Certificate / profile (if configured via env)
    profile_dir = os.getenv("CHROME_PROFILE_DIR")
    if profile_dir:
        opts.add_argument(f"--user-data-dir={profile_dir}")

    return opts


@asynccontextmanager
async def selenium_driver(
    headless: bool = True,
    remote_url: str | None = None,
) -> AsyncIterator[WebDriver]:
    """Async context manager that yields a configured Chrome WebDriver.

    Cleans up (quits) automatically on exit.

    Parameters
    ----------
    headless:
        Run Chrome in headless mode (default True). Set False for debugging.
    remote_url:
        Selenium Grid / Remote WebDriver URL.  When ``None`` a local
        chromedriver is spawned.
    """
    driver: WebDriver

    if remote_url:
        opts = _build_chrome_options(headless)
        driver = webdriver.Remote(command_executor=remote_url, options=opts)
        logger.info("Remote WebDriver connected → %s", remote_url)
    else:
        opts = _build_chrome_options(headless)
        driver = webdriver.Chrome(options=opts)
        logger.info("Local ChromeDriver started (headless=%s)", headless)

    driver.implicitly_wait(2)

    # Anti-detection: override navigator.webdriver et al
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en']});
            """
        })
    except Exception:
        pass

    try:
        yield driver
    except Exception:
        _save_failure_screenshot(driver)
        raise
    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Wait helpers
# ---------------------------------------------------------------------------


class SeleniumWaits:
    """Convenience wrappers around ``WebDriverWait`` with sensible defaults."""

    DEFAULT_TIMEOUT = 30  # seconds

    def __init__(self, driver: WebDriver, timeout: int = DEFAULT_TIMEOUT):
        self._driver = driver
        self._timeout = timeout
        self._wait = WebDriverWait(driver, timeout)

    # -- element retrieval ------------------------------------------------

    def for_clickable(self, by: str, value: str) -> WebElement:
        return self._wait.until(EC.element_to_be_clickable((by, value)))

    def for_visible(self, by: str, value: str) -> WebElement:
        return self._wait.until(EC.visibility_of_element_located((by, value)))

    def for_present(self, by: str, value: str) -> WebElement:
        return self._wait.until(EC.presence_of_element_located((by, value)))

    def all_visible(self, by: str, value: str) -> list[WebElement]:
        return self._wait.until(
            EC.visibility_of_all_elements_located((by, value))
        )

    # -- conditions -------------------------------------------------------

    def until_url_contains(self, fragment: str) -> bool:
        return self._wait.until(EC.url_contains(fragment))

    def until_title_contains(self, fragment: str) -> bool:
        return self._wait.until(EC.title_contains(fragment))


# ---------------------------------------------------------------------------
# Retry decorator (for network flakiness)
# ---------------------------------------------------------------------------

retry_on_transient = retry(
    retry=retry_if_exception_type(RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Screenshot helper
# ---------------------------------------------------------------------------


def _save_failure_screenshot(driver: WebDriver) -> None:
    """Save a timestamped screenshot to ``data/logs/`` for post-mortems."""
    try:
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = log_dir / f"screenshot_error_{ts}.png"
        driver.save_screenshot(str(path))
        logger.error("Error screenshot saved → %s", path)
    except Exception as exc:
        logger.warning("Could not save screenshot: %s", exc)
