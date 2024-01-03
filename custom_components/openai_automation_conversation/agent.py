from __future__ import annotations
import logging
import os
import time
import openai
from homeassistant.components import conversation
from homeassistant.components.conversation import agent
from homeassistant.config import AUTOMATION_CONFIG_PATH
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, MATCH_ALL, SERVICE_RELOAD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import intent, template
from homeassistant.helpers import entity_registry as er
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml, parse_yaml
from homeassistant.components.automation.config import (
    DOMAIN as CONFIG_DOMAIN,
)

from .prompt import AUTOMATION_SYSTEM_PROMPT
from .const import OPENAI_TOKEN

_LOGGER = logging.getLogger(__name__)


class OpenAIAutomationAgent(conversation.AbstractConversationAgent):
    """OpenAIAutomation conversation agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.ent_reg = er.async_get(self.hass)
        self.entry = entry
        self.history: dict[str, list[dict]] = {}

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return MATCH_ALL

    @property
    def attribution(self) -> agent.Attribution:
        """Return the attribution."""
        return {
            "name": "OpenAI Automation Conversation Agent",
            "url": "https://openai.com",
        }

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a sentence."""

        # query openai for automation config
        try:
            automation_content = self.query_openai(user_input.text)
        except TemplateError as err:
            _LOGGER.error("Error rendering prompt: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I had a problem with my template: {err}",
            )
            return conversation.ConversationResult(response=intent_response)
        except openai.OpenAIError as err:
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I had a problem talking to OpenAI: {err}",
            )
            return conversation.ConversationResult(response=intent_response)

        # append and save new automation config
        automation_yaml = parse_yaml(automation_content)
        automation_yaml[CONF_ID] = str(int(time.time() * 1000))
        path = self.hass.config.path(AUTOMATION_CONFIG_PATH)
        current = await read_config(self.hass, path)
        current.append(automation_yaml)

        await self.hass.async_add_executor_job(_write, path, current)
        self.hass.async_create_task(post_write_hook(self.hass))

        # respond to user
        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(
            f"Created automation with id {automation_yaml[CONF_ID]}"
        )
        return conversation.ConversationResult(response=intent_response)

    def query_openai(self, user_input: str) -> str:
        client = openai.OpenAI(api_key=self.entry.data[OPENAI_TOKEN])

        system_content = template.Template(
            AUTOMATION_SYSTEM_PROMPT, self.hass
        ).async_render(
            {
                "ha_name": self.hass.config.location_name,
            },
            parse_result=False,
        )

        _LOGGER.debug("User prompt: %s", user_input)
        _LOGGER.debug("System prompt: %s", system_content)

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_input},
            ],
            model="gpt-3.5-turbo",
        )
        _LOGGER.debug("Response %s", chat_completion.choices[0].message.content)
        return chat_completion.choices[0].message.content


async def read_config(hass, path):
    """Read the config."""
    current = await hass.async_add_executor_job(_read, path)
    if not current:
        current = []
    return current


def _read(path):
    """Read YAML helper."""
    if not os.path.isfile(path):
        return None

    return load_yaml(path)


def _write(path, data):
    """Write YAML helper."""
    # Do it before opening file. If dump causes error it will now not
    # truncate the file.
    contents = dump(data)
    write_utf8_file_atomic(path, contents)


async def post_write_hook(hass):
    """post_write_hook that reloads automations."""
    await hass.services.async_call(CONFIG_DOMAIN, SERVICE_RELOAD)
