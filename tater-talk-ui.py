import asyncio

from nicegui import ui

class ChatDemo:
    def __init__(self):
        # conversation data
        self.system_prompt = ""
        # UI attributes
        self.dark_setting = ui.dark_mode(value=True)
        self.main_panel = None
        # scroll area to put the messages in
        self.message_container = None
        self.current_message = None
        self.setup_ui()

    def setup_ui(self):
        # define navigation tabs
        with ui.tabs().classes('w-full') as tabs:
            tab_main = ui.tab('Main')
            self.tab_memory = ui.tab('Memory')
            self.tab_archive = ui.tab('Archive')
            self.tab_settings = ui.tab("Settings")
        # define contents of each tab
        with ui.tab_panels(tabs, value=tab_main).classes('w-full'):
            self.main_panel = ui.tab_panel(tab_main)
            with self.main_panel:
                ta_sys_msg = ui.textarea(
                    label="System message:"
                )
                ta_sys_msg.bind_value(target_object=self, target_name="system_prompt")
                self.message_container = ui.scroll_area()
                ui.button("Send message", on_click=self.send)
            with ui.tab_panel(self.tab_memory):
                ui.label('Second tab')
            with ui.tab_panel(self.tab_archive):
                ui.label('Archived messages:')
            with ui.tab_panel(self.tab_settings):
                ui.label('Temperature:')
                # toggle to control light/dark theme
                ui.switch('Dark mode').bind_value(self.dark_setting)

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

demo = ChatDemo()
ui.run(host='127.0.0.1', port=9091, title="Tater Talk")