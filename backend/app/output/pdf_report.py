from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


NAVY = colors.HexColor("#101B39")
INDIGO = colors.HexColor("#5B63DA")
ORANGE = colors.HexColor("#F26F32")
TEAL = colors.HexColor("#139A7D")
INK = colors.HexColor("#263149")
MUTED = colors.HexColor("#6F7B92")
LINE = colors.HexColor("#DFE4EC")
PAPER = colors.HexColor("#F6F8FB")


def _time(value: str | None) -> str:
    if not value:
        return "-"
    parsed = datetime.fromisoformat(value)
    return parsed.strftime("%d %b %Y, %I:%M %p")


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(value or "-"), style)


def build_plan_pdf(payload: dict[str, Any]) -> bytes:
    """Create a polished, static plan report from the public schedule response."""
    stream = io.BytesIO()
    page_width, _ = landscape(A4)
    doc = SimpleDocTemplate(
        stream, pagesize=landscape(A4), leftMargin=14*mm, rightMargin=14*mm,
        topMargin=16*mm, bottomMargin=15*mm, title="BlockSangam Planning Report",
        author="BlockSangam",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY, alignment=TA_LEFT, spaceAfter=4)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontSize=9, leading=13, textColor=MUTED)
    kicker = ParagraphStyle("Kicker", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=INDIGO, spaceAfter=3)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK, spaceBefore=9, spaceAfter=7)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=INK)
    small = ParagraphStyle("Small", parent=body, fontSize=6.5, leading=8, textColor=MUTED)
    metric_value = ParagraphStyle("MetricValue", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=NAVY)

    scenario = payload.get("scenario", "base")
    scenario_name = scenario.get("name", scenario.get("id", "scenario")) if isinstance(scenario, dict) else scenario
    summary = payload.get("summary", {})
    solver = payload.get("solver", {})
    entries = payload.get("schedule_entries", [])
    blocks = payload.get("blocks", [])
    unscheduled = payload.get("unscheduled", [])
    validation = payload.get("validation", {})

    story = [
        _p("BLOCKSANGAM / PLANNING REPORT", kicker),
        _p("Constraint-verified maintenance plan", title),
        _p(f"Scenario: {str(scenario_name).replace('_', ' ').title()} | Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')} | Advisory prototype", subtitle),
        Spacer(1, 7*mm),
    ]
    metrics = [
        ("Plan status", payload.get("status", "-"), INDIGO),
        ("Solver", solver.get("status", "-"), TEAL),
        ("Scheduled work", f"{summary.get('tasks_scheduled', len(entries))} / {summary.get('tasks_considered', len(entries)+len(unscheduled))}", ORANGE),
        ("Joint blocks", summary.get("joint_blocks", len(blocks)), INDIGO),
        ("Validation", payload.get("validation_status", "-"), TEAL),
    ]
    metric_cells = []
    for label, value, accent in metrics:
        card = Table([[_p(label.upper(), kicker)], [_p(value, metric_value)]], colWidths=[(page_width-28*mm)/5-4*mm])
        card.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.white),("BOX",(0,0),(-1,-1),.7,LINE),("LINEBEFORE",(0,0),(0,-1),3,accent),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        metric_cells.append(card)
    metric_table = Table([metric_cells], colWidths=[(page_width-28*mm)/5]*5, hAlign="LEFT")
    metric_table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2)]))
    story += [metric_table, Spacer(1, 6*mm), _p("SCHEDULED WORK PACKAGES", heading)]

    schedule_rows = [[_p(x, kicker) for x in ("Task", "Department", "Corridor", "Work type", "Schedule", "Duration", "Priority", "Resources")]]
    for item in entries:
        schedule_rows.append([
            _p(item.get("task_id"), body), _p(item.get("department"), body),
            _p(f"{item.get('section')} {item.get('line')}", body), _p(item.get("task_type"), body),
            _p(f"{_time(item.get('start_time'))}<br/>{_time(item.get('end_time'))}", small),
            _p(f"{item.get('duration_minutes', 0)} min", body),
            _p(f"{round(float(item.get('priority', 0))*100)} / 100<br/>{item.get('priority_band', '')}", body),
            _p(", ".join(item.get("resource_ids", [])) or "-", small),
        ])
    widths = [19*mm, 27*mm, 34*mm, 42*mm, 45*mm, 18*mm, 22*mm, 35*mm]
    schedule_table = Table(schedule_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    schedule_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),NAVY),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),.45,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PAPER]),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(schedule_table)

    if unscheduled:
        story += [Spacer(1, 5*mm), _p("EXCEPTIONS", heading)]
        exception_rows = [[_p(x, kicker) for x in ("Task", "Department", "Reason", "Explanation")]]
        for item in unscheduled:
            exception_rows.append([_p(item.get("task_id"), body), _p(item.get("department"), body), _p(item.get("reason_code"), body), _p(item.get("explanation"), small)])
        exception_table = Table(exception_rows, colWidths=[27*mm,25*mm,48*mm,145*mm], repeatRows=1)
        exception_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#FFF0EB")),("GRID",(0,0),(-1,-1),.45,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
        story.append(exception_table)

    issue_count = len(validation.get("errors", [])) + len(validation.get("warnings", []))
    story += [Spacer(1, 5*mm), KeepTogether([_p("ASSURANCE", heading), _p(f"Independent validation: {payload.get('validation_status', '-')} | {issue_count} reported issues | Solver objective: {solver.get('objective_value', '-')}", body)])]

    def footer(canvas, document):
        canvas.saveState(); canvas.setStrokeColor(LINE); canvas.line(14*mm, 11*mm, page_width-14*mm, 11*mm)
        canvas.setFont("Helvetica", 6.5); canvas.setFillColor(MUTED)
        canvas.drawString(14*mm, 7*mm, "BlockSangam - advisory planning prototype; not an operational railway block grant.")
        canvas.drawRightString(page_width-14*mm, 7*mm, f"Page {document.page}"); canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
