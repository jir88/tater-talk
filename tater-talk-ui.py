import json
import uuid

from nicegui import app, binding, ui, events, elements
from typing import List

from root_cellar.llm import OpenAILLM
from root_cellar.entity import JSONEntityManager, GenEntity
from root_cellar.manager import ChatThread, StructuredHierarchicalMemory, StructuredHierarchicalManager

class TaterTalkUI:
    # make UI settings into bindable properties to make updates more efficient
    main_llm_key = binding.BindableProperty()
    main_llm_url = binding.BindableProperty()
    main_llm_model = binding.BindableProperty()
    main_llm_samp = binding.BindableProperty()

    summary_llm_key = binding.BindableProperty()
    summary_llm_url = binding.BindableProperty()
    summary_llm_model = binding.BindableProperty()
    summary_llm_samp = binding.BindableProperty()

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

        # status flags
        self.generation_status: str = "idle"

        # UI attributes
        self.dark_setting = ui.dark_mode(value=True)
        self.main_panel = None
        # toggle manual editing
        self.check_manual_editing:elements.checkbox.Checkbox = None
        # scroll area to put the messages in
        self.message_container:elements.scroll_area.ScrollArea = None
        # list of chat messages in case we need to mess with them
        self.chat_message_list:List[elements.chat_message.ChatMessage] = []
        # text area for manually editing chat messages
        self.ta_manual_chat_edit:elements.textarea.Textarea = None
        # text input containing the user's message
        self.input_message:elements.textarea.Textarea = None
        # button for submitting the user's message or stopping
        self.button_submit:elements.button.Button = None
        # label for reporting generation speed
        self.label_gen_speed = None
        # toggle memory editing
        self.check_memory_manual_editing:elements.checkbox.Checkbox = None
        # scroll area to put memories in
        self.memory_container = None
        # text area for manually editing memories
        self.ta_manual_memory_edit:elements.textarea.Textarea = None
        # memory settings
        self.ta_summary_prompt:elements.textarea.Textarea = None
        self.num_max_context_prop:elements.number.Number = None
        self.num_max_summary_prop:elements.number.Number = None
        self.num_max_summary_levels:elements.number.Number = None
        self.num_tokens_summarized:elements.number.Number = None
        # entity settings
        self.ta_entity_prompt:elements.textarea.Textarea = None
        self.list_entities:elements.list.List = None
        self.input_entity_name:elements.input.Input = None
        self.ta_entity_description:elements.textarea.Textarea = None
        self.selected_entity:GenEntity = None

        # context size dialog
        self.dialog_context_display:elements.dialog.Dialog = ui.dialog()

        # scroll area to put archived messages in
        self.archive_container:elements.scroll_area.ScrollArea = None
        # LLM settings
        self.main_llm_key = llm.api_key
        self.main_llm_url = llm.base_url
        self.main_llm_model = llm.model
        self.main_llm_samp = json.dumps(
            llm.sampling_options,
            indent=2
        )
        # memory LLM settings
        self.summary_llm_key = summary_llm.api_key
        self.summary_llm_url = summary_llm.base_url
        self.summary_llm_model = summary_llm.model
        self.summary_llm_samp = json.dumps(
            summary_llm.sampling_options,
            indent=2
        )
        # build the GUI
        self.setup_ui()

    def setup_ui(self):
        chat_manager = app.storage.client['manager']
        # define navigation tabs
        with ui.header().classes('bg-dark'):
            with ui.tabs().classes('w-full') as tabs:
                tab_main = ui.tab('Main')
                self.tab_memory = ui.tab('Memory')
                self.tab_archive = ui.tab('Archive')
                self.tab_settings = ui.tab("Settings")
        # define contents of each tab
        with ui.tab_panels(tabs, value=tab_main).classes('w-7/8'):

            # ------ MAIN TAB -------------

            self.main_panel = ui.tab_panel(tab_main)
            with self.main_panel:
                self.ta_sys_msg = ui.textarea(
                    label="System message:",
                    value=chat_manager.chat_memory.chat_thread.system_prompt
                )
                self.ta_sys_msg.classes("w-full")
                self.ta_sys_msg.on("blur", handler=self.update_system_prompt)
                self.check_manual_editing = ui.checkbox(
                    text="Manual editing mode",
                    value=False,
                    on_change=self.toggle_manual_message_editing,
                )
                self.message_container = ui.scroll_area().classes("w-full")
                with ui.row(align_items="center").classes("w-full"):
                    self.input_message = ui.textarea().classes("w-1/2")
                    self.input_message.on("keydown.enter", self.send)
                    self.button_submit = ui.button(icon="send", on_click=self.send)
                    ui.button(icon="replay", on_click=self.regenerate_response)
                # insert label to display generation speed
                self.label_gen_speed = ui.label("Response generation rate: -- Tk/sec | Context length: 0")
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
                    ui.button("Save session", on_click=self.handle_save)

            # ------------- MEMORY TAB --------------

            with ui.tab_panel(self.tab_memory):
                self.ta_summary_prompt = ui.textarea(
                    label="Summarization prompt:"
                ).classes("w-full")
                self.ta_summary_prompt.on('blur', self.update_memory_settings)
                with ui.row().classes("w-full"):
                    self.num_max_context_prop = ui.number(
                        label="Maximum context proportion threshold:",
                        value=0.8,
                        min=0.0, max=1.0, step=0.05,
                        on_change=self.update_memory_settings,
                    ).classes("w-1/3")
                    self.num_max_summary_prop = ui.number(label="Maximum summary proportion:",
                        value=0.5,
                        min=0.0, max=1.0, step=0.05,
                        on_change=self.update_memory_settings,
                    ).classes("w-1/3")
                    self.num_max_summary_levels = ui.number(label="Maximum number of summary levels:",
                        value=3,
                        min=0, step=1,
                        on_change=self.update_memory_settings,
                    ).classes("w-1/3")
                    self.num_tokens_summarized = ui.number(label="Number of tokens to summarize:",
                        value=1024,
                        min=128, step=128,
                        on_change=self.update_memory_settings,
                    ).classes("w-1/3")
                
                self.check_memory_manual_editing = ui.checkbox(
                    text="Manual memory editing",
                    value=False,
                    on_change=self.toggle_manual_memory_editing,
                )
                self.memory_container = ui.scroll_area().classes("w-full")
                
                self.ta_entity_prompt = ui.textarea(
                    label="Entity list prompt:"
                )
                self.ta_entity_prompt.classes("w-full")
                self.ta_entity_prompt.on('blur', self.update_entity_prompt)
                # list of entities
                with ui.row().classes("w-full"):
                    with ui.scroll_area().classes("w-1/4"):
                        self.list_entities = ui.list()
                    with ui.column().classes("w-2/3"):
                        self.input_entity_name = ui.input(placeholder="Entity name").classes("w-full")
                        self.input_entity_name.on('blur', self.update_selected_entity_data)
                        self.input_entity_name.disable()
                        self.ta_entity_description = ui.textarea(placeholder="Entity description").classes("w-full")
                        self.ta_entity_description.on('blur', self.update_selected_entity_data)
                        self.ta_entity_description.disable()
                with ui.row():
                    ui.button(on_click=self.add_entity, icon="add")
                    ui.button(on_click=self.remove_entity, icon="delete")
                with ui.row():
                    ui.button("Calculate context size", on_click=self.display_context_size)
                    ui.button("Update memory", on_click=self.do_memory_update)
            
            # ---------------- ARCHIVE TAB -------------------

            with ui.tab_panel(self.tab_archive):
                ui.label('Archived messages:')
                self.archive_container = ui.scroll_area().classes("w-full")
            
            # ---------------- SETTINGS TAB -------------------

            with ui.tab_panel(self.tab_settings):
                # toggle to control light/dark theme
                ui.switch('Dark mode').bind_value(self.dark_setting)
                # main LLM controls
                # main API key
                input_element = ui.input(
                    label="Main LLM API key:",
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'main_llm_key')
                # main LLM URL
                input_element = ui.input(
                    label="Main LLM URL:",
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'main_llm_url')
                # main LLM name
                input_element = ui.input(
                    label="Main LLM:",
                    placeholder="LLM name",
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
                input_element = ui.input(
                    label="Memory LLM API key:",
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'summary_llm_key')
                input_element = ui.input(
                    label="Memory LLM URL:",
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'summary_llm_url')
                input_element = ui.input(
                    label="Memory LLM:",
                    placeholder="LLM name",
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'summary_llm_model')
                input_element = ui.textarea(
                    label="Memory LLM sampling parameters:"
                ).classes("w-full")
                input_element.on("blur", self.update_llm_settings)
                input_element.bind_value(self, 'summary_llm_samp')

    async def send(self, e:events.GenericEventArguments):
        # if user pressed shift+enter, add a newline
        if hasattr(e, 'args') and e.args['shiftKey']:
            self.input_message.value += "\n"
            return
        # if status is 'responding', we need to stop
        if self.generation_status == 'responding':
            self.generation_status = 'idle'
            return
        # otherwise, send the message

        # get the chat manager
        manager = app.storage.client['manager']
        # get the message the user wants to send
        msg = self.input_message.value.strip()
        # add it to the manager
        manager.append_message({
            'role': 'user',
            'content': msg,
        })
        # disable the message box while LLM is responding
        self.input_message.disable()
        # clear the message box
        self.input_message.value = ""
        # Create message immediately with loading text
        with self.message_container:
            # add user message as outgoing message
            user_message = ui.chat_message(name="User", sent=True)
            # add it to the list of messages
            self.chat_message_list.append(user_message)
            # put in the content
            with user_message:
                ui.markdown(content=msg)
            # add placeholder LLM message while we wait for response
            current_message = ui.chat_message(
                name="Assistant"
            )
            # add it to the list of messages
            self.chat_message_list.append(current_message)
            with current_message:
                part = ui.markdown("Thinking...")
            # scroll new message into view
            self.message_container.scroll_to(percent=1.0)

        # turn the submit button into a stop button
        self.button_submit.set_icon('stop')
        # set status to 'responding'
        self.generation_status = 'responding'

        # Process stream
        o_gen = manager.get_response(stream=True)
        full_response = ""
        async for chunk in o_gen:
            response = chunk['response']
            if response is not None:
                full_response += response
                # print(response, end="", flush=True)  # Shows up in terminal
                part.set_content(full_response)
            if chunk.get('predicted_per_second') is not None:
                context_length = chunk['cache_n'] + chunk['prompt_n'] + chunk['predicted_n']
                self.label_gen_speed.text = "Response generation rate: " + str(round(chunk['predicted_per_second'], 2)) + \
                    " Tk/sec | Context length: " + str(context_length)
            # scroll content into view, in case we've wrapped to a new line
            self.message_container.scroll_to(percent=1.0)
            # check to see if the user has clicked stop
            if self.generation_status == 'idle':
                await o_gen.aclose()
                break
        manager.append_message({
            'role': 'assistant',
            'content': full_response
        })
        # set status to 'idle'
        self.generation_status = 'idle'
        # turn the stop button into a submit button
        self.button_submit.set_icon('send')
        # enable input again
        self.input_message.enable()
        self.input_message.run_method("focus")
    
    async def regenerate_response(self, e:events.GenericEventArguments):
        """
        Deletes the last AI response and regenerates it.
        """
        # if we don't have any messages, there's nothing to regenerate
        if len(self.chat_message_list) == 0:
            ui.notify("There is no LLM message to regenerate!", type='warning')
            return

        # get the chat manager
        manager = app.storage.client['manager']
        # remove the last message, which will be the LLM message we want to regenerate
        manager.chat_memory.chat_thread.messages.pop()
        # also remove it from the GUI
        last_chat_message = self.chat_message_list.pop()
        last_chat_message.delete()
        # disable the message box while LLM is responding
        self.input_message.disable()
        # Create message immediately with loading text
        with self.message_container:
            # add placeholder LLM message while we wait for response
            current_message = ui.chat_message(
                name="Assistant"
            )
            # add it to the list of messages
            self.chat_message_list.append(current_message)
            with current_message:
                part = ui.markdown("Thinking...")
            # scroll new message into view
            self.message_container.scroll_to(percent=1.0)

        # turn the submit button into a stop button
        self.button_submit.set_icon('stop')
        # set status to 'responding'
        self.generation_status = 'responding'

        # Process stream
        o_gen = manager.get_response(stream=True)
        full_response = ""
        async for chunk in o_gen:
            response = chunk['response']
            if response is not None:
                full_response += response
                # print(response, end="", flush=True)  # Shows up in terminal
                part.set_content(full_response)
            if chunk.get('predicted_per_second') is not None:
                context_length = chunk['cache_n'] + chunk['prompt_n'] + chunk['predicted_n']
                self.label_gen_speed.text = "Response generation rate: " + str(round(chunk['predicted_per_second'], 2)) + \
                    " Tk/sec | Context length: " + str(context_length)
            # scroll content into view, in case we've wrapped to a new line
            self.message_container.scroll_to(percent=1.0)
            # check to see if the user has clicked stop
            if self.generation_status == 'idle':
                await o_gen.aclose()
                break
        manager.append_message({
            'role': 'assistant',
            'content': full_response
        })
        # set status to 'idle'
        self.generation_status = 'idle'
        # turn the stop button into a submit button
        self.button_submit.set_icon('send')
        # enable input again
        self.input_message.enable()
        self.input_message.run_method("focus")

    def update_system_prompt(self):
        """Pull the current value of ta_sys_msg and push it into the system prompt."""
        app.storage.client['manager'].chat_memory.chat_thread.system_prompt = self.ta_sys_msg.value
    
    def update_memory_settings(self):
        """Update the chat manager with current memory settings."""
        app.storage.client['manager'].chat_memory.summary_prompt = self.ta_summary_prompt.value
        app.storage.client['manager'].chat_memory.prop_ctx = self.num_max_context_prop.value
        app.storage.client['manager'].chat_memory.prop_summary = self.num_max_summary_prop.value
        app.storage.client['manager'].chat_memory.n_levels = self.num_max_summary_levels.value
        app.storage.client['manager'].chat_memory.n_tok_summarize = self.num_tokens_summarized.value
    
    def update_llm_settings(self):
        """Update chat manager with current LLM settings."""
        print("Updating LLM settings!")
        main_llm = app.storage.client['manager'].llm
        summary_llm = app.storage.client['manager'].chat_memory.summary_llm
        # main LLM settings
        main_llm.api_key = self.main_llm_key
        main_llm.base_url = self.main_llm_url
        main_llm.model = self.main_llm_model
        main_llm.sampling_options = json.loads(s=self.main_llm_samp)
        # summary LLM settings
        summary_llm.api_key = self.summary_llm_key
        summary_llm.base_url = self.summary_llm_url
        summary_llm.model = self.summary_llm_model
        summary_llm.sampling_options = json.loads(s=self.summary_llm_samp)

    async def handle_upload(self, e: events.UploadEventArguments):
        """
        Uploads a saved session and populates the UI.
        """
        # make sure manual message editing is toggled off
        self.check_manual_editing.value = False
        self.check_memory_manual_editing.value = False

        # load the file
        saved_session_text = await e.file.text()
        chat_manager = StructuredHierarchicalManager.model_validate_json(json_data=saved_session_text)
        app.storage.client['manager'] = chat_manager
        # update settings
        self.main_llm_key = chat_manager.llm.api_key
        self.main_llm_url = chat_manager.llm.base_url
        self.main_llm_model = chat_manager.llm.model
        self.main_llm_samp = json.dumps(chat_manager.llm.sampling_options, indent=2)

        summary_llm = chat_manager.chat_memory.summary_llm
        self.summary_llm_key = summary_llm.api_key
        self.summary_llm_url = summary_llm.base_url
        self.summary_llm_model = summary_llm.model
        self.summary_llm_samp = json.dumps(summary_llm.sampling_options, indent=2)

        # update the system message
        self.ta_sys_msg.value = app.storage.client['manager'].chat_memory.chat_thread.system_prompt
        # update the list of messages
        self.refresh_message_list()

        # update memory settings
        self.ta_summary_prompt.value = app.storage.client['manager'].chat_memory.summary_prompt
        self.num_max_context_prop.value = app.storage.client['manager'].chat_memory.prop_ctx
        self.num_max_summary_prop.value = app.storage.client['manager'].chat_memory.prop_summary
        self.num_max_summary_levels.value = app.storage.client['manager'].chat_memory.n_levels
        self.num_tokens_summarized.value = app.storage.client['manager'].chat_memory.n_tok_summarize
        # refresh memory list
        self.refresh_memory_list()

        # update entity settings
        self.ta_entity_prompt.value = app.storage.client['manager'].chat_memory.entity_manager.prompt_entity_list
        self.refresh_entity_list()

        # update the list of archived messages
        self.refresh_archived_message_list()

    def handle_save(self):
        """Save the session to a JSON file."""
        output_file_txt = app.storage.client['manager'].model_dump_json(indent=2)
        # show save dialog
        ui.download.content(
            content=output_file_txt,
            filename="session.json",
            media_type="application/json"
        )
    
    def refresh_message_list(self):
        """Delete current message list in the GUI and rebuild it from the chat manager."""
        # clear the message elements
        self.message_container.clear()
        # clear the list where we keep track of message elements
        self.chat_message_list = []
        # add the conversation messages back
        chat_manager = app.storage.client['manager']
        with self.message_container:
            for msg in chat_manager.chat_memory.chat_thread.messages:
                is_sent = msg['role'] == "user"
                current_message = ui.chat_message(
                    name=msg['role'],
                    sent=is_sent
                )
                # add it to the list of messages
                self.chat_message_list.append(current_message)
                # format content as markdown
                with current_message:
                    ui.markdown(msg['content'])
        # scroll messages into view
        self.message_container.scroll_to(percent=1.0)

    def refresh_archived_message_list(self):
        """Delete current archived message list in the GUI and rebuild it from the chat manager."""
        # clear the message elements
        self.archive_container.clear()
        # add the archived messages back
        chat_manager = app.storage.client['manager']
        with self.archive_container:
            for msg in chat_manager.chat_memory.chat_thread.archived_messages:
                is_sent = msg['role'] == "user"
                current_message = ui.chat_message(
                    name=msg['role'],
                    sent=is_sent
                )
                # format content as markdown
                with current_message:
                    ui.markdown(msg['content'])
        # scroll last archived message into view
        self.archive_container.scroll_to(percent=1.0)
    
    def toggle_manual_message_editing(self, e:events.ValueChangeEventArguments):
        """Switch between chat message view and editable text view."""
        # if we're switching back to chat mode
        if not e.value:
            app.storage.client['manager'].chat_memory.chat_thread.import_readable(self.ta_manual_chat_edit.value)
            self.refresh_message_list()
        else:
            # nuke chat messages
            self.message_container.clear()
            self.chat_message_list = []
            # get readable text
            chat_txt = app.storage.client['manager'].chat_memory.chat_thread.format_readable()
            # add text area
            with self.message_container:
                self.ta_manual_chat_edit = ui.textarea(value=chat_txt).classes("w-full")
            self.message_container.scroll_to(percent=1.0)
    
    def refresh_memory_list(self):
        """Refresh the list of memories displayed in the GUI."""
        chat_manager = app.storage.client['manager']

        # clear old memories
        self.memory_container.clear()

        if len(chat_manager.chat_memory.all_memory) == 0:
            # no memories
            return
        # add memories
        with self.memory_container:
            for msg in chat_manager.chat_memory.all_memory:
                current_message = ui.chat_message(
                    name="Level " + str(msg['level']),
                    sent=False
                )
                # format content as markdown
                with current_message:
                    ui.markdown(msg['content'])
    
    def toggle_manual_memory_editing(self, e:events.ValueChangeEventArguments):
        """Switch between chat message view and editable text view."""
        # when the text area changes, put the new version into the session
        # st.session_state.chat_session.chat_memory.import_readable(st.session_state.ta_mem_editor)
        # if we're switching back to chat mode
        if not e.value:
            app.storage.client['manager'].chat_memory.import_readable(self.ta_manual_memory_edit.value)
            self.refresh_memory_list()
        else:
            # nuke memory messages
            self.memory_container.clear()
            # get readable text
            mem_txt = app.storage.client['manager'].chat_memory.format_readable()
            # add text area
            with self.memory_container:
                self.ta_manual_memory_edit = ui.textarea(value=mem_txt).classes("w-full")
            self.memory_container.scroll_to(percent=1.0)
    
    def update_entity_prompt(self):
        app.storage.client['manager'].chat_memory.entity_manager.prompt_entity_list = self.ta_entity_prompt.value
    
    def refresh_entity_list(self):
        """Rebuild the GUI list of entities."""
        # clear the list
        self.list_entities.clear()
        # add the current entities
        with self.list_entities:
            entity_list = app.storage.client['manager'].chat_memory.entity_manager.entity_list.entities
            for entity in entity_list:
                ui.item(
                    text=entity.name,
                    # lambda wrapper required to call method with proper entity instead
                    # of the last entity in the list
                    on_click=lambda e, entity=entity: self.select_entity_item(entity=entity)
                )
        # if there are any entities
        if len(entity_list) > 0:
            # enable the editor inputs
            self.input_entity_name.enable()
            self.ta_entity_description.enable()
            # select first entity by default
            self.select_entity_item(entity_list[0])
        else:
            # disable the editor inputs
            self.input_entity_name.disable()
            self.ta_entity_description.disable()
    
    def select_entity_item(self, entity):
        """Handle user selecting an entity."""
        self.selected_entity = entity
        # put entity info in inputs
        self.input_entity_name.value = entity.name
        self.ta_entity_description.value = entity.description
    
    def update_selected_entity_data(self):
        """Update the data for the currently selected entity when the user changes it."""
        if self.selected_entity is None:
            return
        original_name = self.selected_entity.name
        self.selected_entity.name = self.input_entity_name.value
        self.selected_entity.description = self.ta_entity_description.value
        # if entity name is being changed, we need to refresh the list
        if original_name != self.input_entity_name.value:
            entity = self.selected_entity
            self.refresh_entity_list()
            # reselect current entity
            self.select_entity_item(entity)
    
    def add_entity(self):
        """Add a new blank entity and enable editing it."""
        # create blank entity and add it
        new_entity = GenEntity(name="", description="")
        app.storage.client['manager'].chat_memory.entity_manager.entity_list.entities.append(new_entity)
        # refresh the list
        self.refresh_entity_list()
        # reselect new entity
        self.select_entity_item(new_entity)

        # enable the editor inputs
        self.input_entity_name.enable()
        self.ta_entity_description.enable()
        self.input_entity_name.run_method("focus")

    def remove_entity(self):
        """Remove the currently selected entity."""
        entity_list = app.storage.client['manager'].chat_memory.entity_manager.entity_list.entities
        if len(entity_list) == 0:
            return # nothing to delete
        
        idx = entity_list.index(self.selected_entity)
        entity_list.remove(self.selected_entity)
        self.refresh_entity_list()
        # if no entities left, clear the entity inputs
        if len(entity_list) == 0:
            self.input_entity_name.value = ""
            self.ta_entity_description.value = ""
            self.input_entity_name.disable()
            self.ta_entity_description.disable()
            return
        # select next entity in the list
        if idx == len(entity_list):
            idx = idx - 1
        self.select_entity_item(entity_list[idx])
    
    def display_context_size(self):
        """Show a dialog with details about context length."""
        # clear old content
        self.dialog_context_display.clear()
        # build new
        chat_manager = app.storage.client['manager']
        with self.dialog_context_display, ui.card():
            total_size = 0
            # calculate size of raw messages
            level_size = 0
            for msg in chat_manager.chat_memory.chat_thread.messages:
                level_size += chat_manager.llm.count_tokens(msg['content'])
            total_size += level_size
            # calculate percent of alloted space
            level_allowance = chat_manager.llm.sampling_options['num_ctx']*chat_manager.chat_memory.prop_ctx
            level_pct = int(level_size/level_allowance*100)
            ui.label(f"Message size: {level_size} ({level_pct}%)")
            for level in range(1, chat_manager.chat_memory.n_levels + 1):
                level_size = chat_manager.chat_memory.summary_level_size(level=level)
                level_allowance = chat_manager.llm.sampling_options['num_ctx']*chat_manager.chat_memory.prop_ctx*chat_manager.chat_memory.prop_summary**level
                level_pct = int(level_size/level_allowance*100)
                ui.label(f"Level {level} size: {level_size} ({level_pct}%)")
                total_size += level_size
            ui.label(f"Total context size: {total_size}")
        # open it
        self.dialog_context_display.open()
    
    async def do_memory_update(self):
        # tell state manager to update memory, ensuring all levels are within limits
        await app.storage.client['manager'].chat_memory.update_all_memory()
        # messages are changed
        self.refresh_message_list()
        # memories are changed
        self.refresh_memory_list()
        # entities are changed
        if len(app.storage.client['manager'].chat_memory.entity_manager.entity_list.entities) > 0:
            self.refresh_entity_list()
        # messages are moved to archive
        self.refresh_archived_message_list()


tater_ui = TaterTalkUI()
ui.run(host='127.0.0.1', port=9091, title="Tater Talk", favicon='🥔')