from agent.component.file_parser import FileParser, FileParserParam
from agent.component.citation_formatter import CitationFormatter


def make_parser(top_n: int = 2) -> FileParser:
    parser = FileParser.__new__(FileParser)
    parser._param = FileParserParam()
    parser._param.top_n = top_n
    return parser


def test_file_parser_layout_recognize_is_configurable():
    param = FileParserParam()
    schema = param.get_config_schema()

    assert "layout_recognize" in schema
    assert schema["layout_recognize"]["allow_custom"] is True
    assert {item["value"] for item in schema["layout_recognize"]["options"]} >= {"Plain Text", "DeepDOC"}

    param.layout_recognize = "DeepDOC"
    param.check()


def test_file_parser_plain_text_health_skips_local_ocr():
    health = FileParser.local_ocr_deepdoc_health("Plain Text")

    assert health["status"] == "ok"
    assert health["healthy"] is True
    assert health["local_ocr_required"] is False
    assert health["checks"][0]["name"] == "layout_mode"


def test_file_parser_deepdoc_health_reports_local_checks_without_deep_probe():
    health = FileParser.local_ocr_deepdoc_health("DeepDOC")

    assert health["layout_recognize"] == "DeepDOC"
    assert health["local_ocr_required"] is True
    assert any(check["name"] == "local_model_files" for check in health["checks"])
    assert not any(check["name"] == "deep_probe" for check in health["checks"])
    assert health["status"] in {"ok", "unhealthy"}


def test_file_parser_expands_legal_topic_terms():
    terms = FileParser._keywords("把和婚姻有关的条款找出来")

    assert "婚姻" in terms
    assert "夫妻" in terms
    assert "离婚" in terms
    assert "有关" not in terms


def test_file_parser_prioritizes_article_text_over_toc_for_legal_queries():
    parser = make_parser(top_n=2)
    chunks = [
        {
            "document_name": "民法典.pdf",
            "content": "目录\n第五编 婚姻家庭 ........ 108\n第一章 一般规定 ........ 109",
            "source_index": 0,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千零四十一条 婚姻家庭受国家保护。实行婚姻自由、一夫一妻、男女平等的婚姻制度。",
            "source_index": 30,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千零七十六条 夫妻双方自愿离婚的，应当签订书面离婚协议。",
            "source_index": 55,
        },
    ]

    matches = parser._select_matches(chunks, "把和婚姻有关的条款找出来")

    assert len(matches) == 2
    assert "目录" not in matches[0]["content"]
    assert all("第" in item["content"] and "条" in item["content"] for item in matches)


def test_file_parser_includes_neighbor_chunks_when_context_window_enabled():
    parser = make_parser(top_n=1)
    parser._param.context_window = 1
    chunks = [
        {
            "document_name": "民法典.pdf",
            "content": "第一千零四十条 本编调整因婚姻家庭产生的民事关系。",
            "source_index": 10,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千零四十一条 婚姻家庭受国家保护。",
            "source_index": 11,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千零四十二条 禁止包办、买卖婚姻和其他干涉婚姻自由的行为。",
            "source_index": 12,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千一百二十一条 继承从被继承人死亡时开始。",
            "source_index": 80,
        },
    ]

    matches = parser._select_matches(chunks, "婚姻家庭受国家保护")

    assert [item["source_index"] for item in matches] == [10, 11, 12]


def test_file_parser_parses_chinese_legal_article_numbers():
    assert FileParser._parse_article_number("十八") == 18
    assert FileParser._parse_article_number("二十四") == 24
    assert FileParser._parse_article_number("一千零四十一") == 1041
    assert FileParser._parse_article_number("1118") == 1118


def test_file_parser_selects_chunks_by_legal_article_range():
    parser = make_parser(top_n=5)
    chunks = [
        {
            "document_name": "民法典.pdf",
            "content": "第一千零三十九条 自然人的个人信息受法律保护。",
            "source_index": 1,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千零四十一条 婚姻家庭受国家保护。",
            "source_index": 2,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千零七十六条 夫妻双方自愿离婚的，应当签订书面离婚协议。",
            "source_index": 3,
        },
        {
            "document_name": "民法典.pdf",
            "content": "第一千一百二十一条 继承从被继承人死亡时开始。",
            "source_index": 4,
        },
    ]

    matches = parser._select_matches(chunks, "请找出第1041条至第1118条")

    assert [item["source_index"] for item in matches] == [2, 3]


def test_file_parser_compact_chunk_includes_page_article_and_source_ref():
    chunk = FileParser._compact_chunk(
        {
            "id": "chunk-1",
            "document_id": "file-1",
            "document_name": "民法典.pdf",
            "page_num_int": [108],
            "content": "第一千零四十一条 婚姻家庭受国家保护。",
            "source_index": 9,
        }
    )

    assert chunk["page"] == 108
    assert chunk["article_numbers"] == [1041]
    assert chunk["source_ref"] == "民法典.pdf | page 108 | chunk chunk-1 | article 1041"


class FakeCanvas:
    def __init__(self):
        self.references = None
        self.values = {
            "sys.query": "婚姻家庭",
            "sys.file_assets": [
                {
                    "id": "file-1",
                    "name": "民法典.pdf",
                    "text": "第一千零四十一条 婚姻家庭受国家保护。",
                }
            ],
        }

    def is_canceled(self):
        return False

    def get_variable_value(self, exp):
        return self.values[exp]

    def get_tenant_id(self):
        return ""

    def add_reference(self, chunks, doc_infos):
        self.references = {"chunks": chunks, "doc_infos": doc_infos}

    def get_component_name(self, _cpn_id):
        return ""


def test_file_parser_references_include_standard_file_id_and_source_ref():
    parser = make_parser(top_n=1)
    parser._canvas = FakeCanvas()

    parser._invoke()

    file_info = parser.output("file_info")
    assert file_info[0]["id"] == "file-1"
    assert file_info[0]["name"] == "民法典.pdf"
    references = parser.output("references")
    assert references[0]["file_id"] == "file-1"
    assert references[0]["document_id"] == "file-1"
    assert references[0]["chunk_id"]
    assert "民法典.pdf" in references[0]["source_ref"]
    assert parser._canvas.references is not None


def test_citation_formatter_normalizes_references_and_formats_markdown():
    citations = CitationFormatter.normalize_references(
        [
            {
                "file_id": "file-1",
                "document_name": "民法典.pdf",
                "chunk_id": "chunk-1",
                "page_num_int": [108],
                "article_numbers": [1041],
                "content": "第一千零四十一条 婚姻家庭受国家保护。",
            }
        ]
    )

    assert citations[0]["file_id"] == "file-1"
    assert citations[0]["page"] == 108
    assert citations[0]["source_ref"] == "民法典.pdf | page 108 | chunk chunk-1 | article 1041"
    markdown = CitationFormatter.format_markdown(citations)
    assert "file_id: file-1" in markdown
    assert "民法典.pdf | page 108 | chunk chunk-1 | article 1041" in markdown
