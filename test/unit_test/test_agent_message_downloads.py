from agent.component.message import Message


class FakeComponent:
    def __init__(self, outputs):
        self.outputs = outputs

    def output(self, name=None):
        if name is None:
            return self.outputs
        return self.outputs.get(name)


class FakeCanvas:
    def __init__(self, components):
        self.components = components

    def get_component_obj(self, component_id):
        return self.components[component_id]


def make_message(upstream, components):
    message = Message.__new__(Message)
    message._canvas = FakeCanvas(components)
    message.get_upstream = lambda: upstream
    return message


def test_message_collects_and_deduplicates_upstream_downloads():
    download = {
        "doc_id": "doc-1",
        "file_name": "report.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size": 128,
        "base64": "hidden",
    }
    message = make_message(
        ["DocGenerator:Report", "ExcelProcessor:Export"],
        {
            "DocGenerator:Report": FakeComponent({"download": download}),
            "ExcelProcessor:Export": FakeComponent({"downloads": [download]}),
        },
    )

    downloads = Message._deduplicate_downloads(message._collect_upstream_downloads())

    assert downloads == [
        {
            "doc_id": "doc-1",
            "filename": "report.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": 128,
        }
    ]
