import json
import uuid

from nicegui import app, binding, ui, events, elements
from typing import List

from root_cellar.llm import OpenAILLM
from root_cellar.entity import JSONEntityManager
from root_cellar.manager import ChatThread, StructuredHierarchicalMemory, StructuredHierarchicalManager

class ChatDemo:
    # make UI settings into bindable properties to make updates more efficient
    main_llm_key = binding.BindableProperty()
    main_llm_url = binding.BindableProperty()
    main_llm_model = binding.BindableProperty()
    main_llm_samp = binding.BindableProperty()

    def __init__(self):
        # set up LLM backend
        llm = OpenAILLM(model="gemma-3n-E4B-it-UD-Q5_K_XL-cpu")
        # separate LLM for summarizing
        summary_llm = OpenAILLM(model="gemma-3n-E4B-it-UD-Q5_K_XL-cpu")
        # initialize session manager
        entity_manager = JSONEntityManager(llm=summary_llm)
        chat_thread = ChatThread(session_id=str(uuid.uuid4()), system_prompt="")
        chat_memory = StructuredHierarchicalMemory(
            summary_llm=summary_llm,
            chat_thread=chat_thread,
            entity_manager=entity_manager
        )
        cs = StructuredHierarchicalManager(
            llm=llm,
            chat_memory=chat_memory
        )
        # put session data in volatile storage
        app.storage.client['manager'] = cs
        # conversation data
        self.system_prompt = ""
        self.messages = []
        # UI attributes
        self.dark_setting = ui.dark_mode(value=True)
        self.main_panel = None
        # scroll area to put the messages in
        self.message_container = None
        self.current_message = None
        # scroll area to put memories in
        self.memory_container = None
        # scroll area to put archived messages in
        self.archive_container = None
        # LLM settings
        self.main_llm_key = cs.llm.api_key
        self.main_llm_url = cs.llm.base_url
        self.main_llm_model = cs.llm.model
        self.main_llm_samp = json.dumps(
            cs.llm.sampling_options,
            indent=2
        )
        # # memory LLM controls
        # ui.input(
        #     label="Memory LLM API key:",
        #     value="sk-placeholder"
        # ).classes("w-full")
        # ui.input(
        #     label="Memory LLM URL:",
        #     value="http://127.0.0.1:8080/v1"
        # ).classes("w-full")
        # ui.input(
        #     label="Memory LLM:",
        #     placeholder="LLM name"
        # ).classes("w-full")
        # ui.textarea(
        #     label="Memory LLM sampling parameters:"
        # ).classes("w-full")
        self.setup_ui()

    def setup_ui(self):
        chat_manager = app.storage.client['manager']
        # define navigation tabs
        with ui.tabs().classes('w-full') as tabs:
            tab_main = ui.tab('Main')
            self.tab_memory = ui.tab('Memory')
            self.tab_archive = ui.tab('Archive')
            self.tab_settings = ui.tab("Settings")
        # define contents of each tab
        with ui.tab_panels(tabs, value=tab_main).classes('w-7/8'):
            self.main_panel = ui.tab_panel(tab_main)
            with self.main_panel:
                self.ta_sys_msg = ui.textarea(
                    label="System message:",
                    value=chat_manager.chat_memory.chat_thread.system_prompt
                )
                self.ta_sys_msg.classes("w-full")
                self.ta_sys_msg.on("blur", handler=self.update_system_prompt)
                ui.checkbox(
                    text="Manual editing mode",
                    value=False
                )
                self.message_container = ui.scroll_area().classes("w-full")
                with ui.row(align_items="center").classes("w-full"):
                    ui.input().classes("w-1/2")
                    ui.button(icon="send", on_click=self.send)
                    ui.button("Regenerate")
                    ui.button("Continue")
                with ui.row():
                    # file uploader to select a saved session
                    saved_session_uploader = ui.upload(
                        on_upload=self.handle_upload,
                        max_file_size=10e6,
                        multiple=False,
                        max_files=1,
                        auto_upload=True,
                        label="Upload saved session:"
                    )
                    saved_session_uploader.props('accept=.json')
                    # button for saving the current session
                    ui.button("Save session")
            with ui.tab_panel(self.tab_memory):
                ta_sum_prompt = ui.textarea(
                    label="Summarization prompt:"
                ).classes("w-full")
                with ui.row().classes("w-full"):
                    ui.number(
                        label="Maximum context proportion threshold:",
                        value=0.8,
                        min=0.0, max=1.0, step=0.05,
                    ).classes("w-1/3")
                    ui.number(label="Maximum summary proportion:",
                        value=0.5,
                        min=0.0, max=1.0, step=0.05,
                    ).classes("w-1/3")
                    ui.number(label="Maximum number of summary levels:",
                        value=3,
                        min=0, step=1,
                    ).classes("w-1/3")
                    ui.number(label="Number of tokens to summarize:",
                        value=1024,
                        min=128, step=128,
                    ).classes("w-1/3")
                
                ui.checkbox(
                    text="Manual memory editing",
                    value=False
                )
                self.memory_container = ui.scroll_area().classes("w-full")
                
                ta_entity_prompt = ui.textarea(
                    label="Entity list prompt:"
                )
                ta_entity_prompt.classes("w-full")
                # list of entities
                with ui.row().classes("w-full"):
                    ui.select(
                        options=[],
                        multiple=False,
                    )
                    with ui.column().classes("w-2/3"):
                        ui.input(placeholder="Entity name").classes("w-full")
                        ui.textarea(placeholder="Entity description").classes("w-full")
                with ui.row():
                    ui.button("Calculate context size")
                    ui.button("Update memory")
            with ui.tab_panel(self.tab_archive):
                ui.label('Archived messages:')
                self.archive_container = ui.scroll_area().classes("w-full")
            with ui.tab_panel(self.tab_settings):
                # toggle to control light/dark theme
                ui.switch('Dark mode').bind_value(self.dark_setting)
                # main LLM controls
                # main API key
                input_element = ui.input(
                    label="Main LLM API key:",
                    value="sk-placeholder",
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'main_llm_key')
                # main LLM URL
                input_element = ui.input(
                    label="Main LLM URL:",
                    value="http://127.0.0.1:8080/v1"
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'main_llm_url')
                # main LLM name
                input_element = ui.input(
                    label="Main LLM:",
                    placeholder="LLM name"
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'main_llm_model')
                # main LLM sampling parameters
                input_element = ui.textarea(
                    label="Main LLM sampling parameters:"
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'main_llm_samp')
                # memory LLM controls
                ui.input(
                    label="Memory LLM API key:",
                    value="sk-placeholder"
                ).classes("w-full")
                ui.input(
                    label="Memory LLM URL:",
                    value="http://127.0.0.1:8080/v1"
                ).classes("w-full")
                ui.input(
                    label="Memory LLM:",
                    placeholder="LLM name"
                ).classes("w-full")
                ui.textarea(
                    label="Memory LLM sampling parameters:"
                ).classes("w-full")

    async def mock_stream(self):
        """Simulate streaming response"""
        response = "Hello! This is a test message that should stream word by word."
        for word in response.split():
            yield word + " "
            await asyncio.sleep(0.5)

    async def send(self):
        # Create message immediately with loading text
        with self.message_container:
            self.current_message = ui.chat_message(
                name="Bot",
                text_html=True,
            )
            with self.current_message:
                part = ui.html("Thinking...")

        # Process stream
        full_response = ""

    def update_system_prompt(self):
        """Pull the current value of ta_sys_msg and push it into the system prompt."""
        app.storage.client['manager'].chat_memory.chat_thread.system_prompt = self.ta_sys_msg.value
    
    def update_llm_settings(self):
        """Update chat manager with current LLM settings."""
        print("Updating LLM settings!")
        manager = app.storage.client['manager']
        # main LLM settings
        manager.llm.api_key = self.main_llm_key
        manager.llm.base_url = self.main_llm_url
        manager.llm.model = self.main_llm_model
        manager.llm.sampling_options = json.loads(s=self.main_llm_samp)

    async def handle_upload(self, e: events.UploadEventArguments):
        """
        Uploads a saved session and populates the UI.
        """
        saved_session_text = await e.file.text()
        print(saved_session_text)

demo = ChatDemo()
ui.run(host='127.0.0.1', port=9091, title="Tater Talk")