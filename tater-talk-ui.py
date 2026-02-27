import asyncio

from nicegui import ui, events

class ChatDemo:
    def __init__(self):
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
        self.setup_ui()

    def setup_ui(self):
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
                ta_sys_msg = ui.textarea(
                    label="System message:"
                )
                ta_sys_msg.classes("w-full")
                ta_sys_msg.bind_value(target_object=self, target_name="system_prompt")
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
                    ui.select(options=[])
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
                ui.input(
                    label="Main LLM:",
                    placeholder="LLM name"
                ).classes("w-full")
                ui.textarea(
                    label="Main LLM sampling parameters:"
                ).classes("w-full")
                # memory LLM controls
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
        async for chunk in self.mock_stream():
            full_response += chunk
            print(chunk, end="", flush=True)  # Shows up in terminal
            part.set_content(full_response)
    
    def update_system_prompt():
        pass

    async def handle_upload(self, e: events.UploadEventArguments):
        """
        Uploads a saved session and populates the UI.
        """
        saved_session_text = await e.file.text()
        print(saved_session_text)

demo = ChatDemo()
ui.run(host='127.0.0.1', port=9091, title="Tater Talk")