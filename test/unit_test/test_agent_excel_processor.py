from agent.component.excel_processor import ExcelProcessor, ExcelProcessorParam
from agent.component.number_calculate import NumberCalculate
from agent.component.chart_spec_builder import ChartSpecBuilder


class FakeCanvas:
    task_id = "task-1"

    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_canceled(self):
        return False

    def is_reff(self, exp):
        return exp in self.variables

    def get_variable_value(self, exp):
        return self.variables.get(exp)


def make_processor(keywords=None) -> ExcelProcessor:
    processor = ExcelProcessor.__new__(ExcelProcessor)
    processor._param = ExcelProcessorParam()
    processor._canvas = FakeCanvas()
    processor._id = "ExcelProcessor:Test"
    if keywords is not None:
        processor._param.aggregate_column_keywords = keywords
    return processor


def test_excel_processor_prefers_total_columns_over_broad_amount_columns():
    processor = make_processor(["total", "amount"])

    matched = processor._match_aggregate_columns(["Amount", "Total Amount", "Description"])

    assert matched == ["Total Amount"]


def test_excel_processor_uses_broad_amount_column_when_no_total_column_exists():
    processor = make_processor(["total", "amount"])

    matched = processor._match_aggregate_columns(["Amount", "Description"])

    assert matched == ["Amount"]


def test_excel_processor_matches_chinese_total_columns():
    processor = make_processor(["合计", "总计", "金额"])

    matched = processor._match_aggregate_columns(["金额", "金额合计", "备注"])

    assert matched == ["金额合计"]


def test_excel_processor_accepts_calculate_and_export_operations():
    param = ExcelProcessorParam()

    param.operation = "calculate"
    assert param.check() is True

    param.operation = "export"
    assert param.check() is True


def test_excel_processor_calculates_number_without_llm():
    processor = make_processor()
    processor._param.calculation_value = "120"
    processor._param.calculation_coefficient = "2.5"
    processor._param.calculation_result_name = "B"

    processor._calculate_number()

    assert processor.output("result") == 300
    assert processor.output("aggregate") == {
        "result_name": "B",
        "value": 120,
        "coefficient": 2.5,
        "result": 300,
        "operation": "multiply",
    }
    assert processor.output("summary") == "B = 120 x 2.5 = 300"


def test_number_calculate_weighted_score_formula_without_llm():
    result = NumberCalculate.weighted_score(
        self_score=86.5,
        self_weight=0.6,
        external_score=92,
        external_weight=0.4,
        round_digits=2,
    )

    assert result == 88.7


def test_chart_spec_builder_generates_line_and_radar_specs():
    records = [
        {"activity": "lesson-1", "score": 82, "pronunciation": 84, "fluency": 80},
        {"activity": "lesson-2", "score": 88, "pronunciation": 90, "fluency": 86},
    ]

    line = ChartSpecBuilder.build_spec(
        "line",
        records,
        title="历史成绩趋势",
        x_field="activity",
        y_field="score",
    )
    radar = ChartSpecBuilder.build_spec(
        "radar",
        records[:1],
        title="多维评分",
        x_field="activity",
        dimensions=["pronunciation", "fluency"],
    )

    assert line == {
        "schema_version": 1,
        "type": "line",
        "title": "历史成绩趋势",
        "encoding": {"x": "activity", "y": "score", "series": ""},
        "data": [
            {"x": "lesson-1", "y": 82.0, "series": None},
            {"x": "lesson-2", "y": 88.0, "series": None},
        ],
    }
    assert radar == {
        "schema_version": 1,
        "type": "radar",
        "title": "多维评分",
        "dimensions": ["pronunciation", "fluency"],
        "series": [
            {
                "label": "lesson-1",
                "values": [
                    {"axis": "pronunciation", "value": 84.0},
                    {"axis": "fluency", "value": 80.0},
                ],
            }
        ],
    }
