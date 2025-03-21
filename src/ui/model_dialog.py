from typing import ClassVar

import llm
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select


class ModelDialog(ModalScreen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ModelDialog {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 3;
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }

    #dialog Button {
        width: 100%;
    }

    #dialog #buttons {
        column-span: 2;
        height: 3;
        align-horizontal: right;
        padding-right: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.models = [(model.model_id, model.model_id) for model in llm.get_models()]
        self.current_model = llm.get_model().model_id

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Select Model:")
            yield Select(
                options=self.models,
                value=self.current_model,
                id="model"
            )
            with Vertical(id="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            selected_model = self.query_one("#model").value
            self.dismiss(selected_model)
        else:
            self.dismiss(None)