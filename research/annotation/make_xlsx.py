"""Write labels_harshul.xlsx (dropdowns, frozen header) from labels_template.csv. Needs openpyxl."""
import csv
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
wb = Workbook()
ws = wb.active
ws.title = "labels"
with open(os.path.join(HERE, "labels_template.csv"), newline="") as f:
    for row in csv.reader(f):
        ws.append(row)
for col, width in zip("ABCDEFGH", (5, 24, 28, 70, 50, 11, 14, 30)):
    ws.column_dimensions[col].width = width
for cell in ws[1]:
    cell.font = Font(bold=True)
for row in ws.iter_rows(min_row=2):
    for cell in row:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
ws.freeze_panes = "F2"
n = ws.max_row
for col, opts in (("F", "y,n"), ("G", "y,partial,n")):
    dv = DataValidation(type="list", formula1=f'"{opts}"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{col}2:{col}{n}")
guide = wb.create_sheet("guide")
with open(os.path.join(HERE, "GUIDE.md")) as f:
    for line in f:
        guide.append([line.rstrip("\n")])
guide.column_dimensions["A"].width = 120
wb.save(os.path.join(HERE, "labels_harshul.xlsx"))
