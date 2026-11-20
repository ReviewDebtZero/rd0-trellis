# make -C research/paper  -> regenerates numbers from research/results and builds the PDF
all: numbers tooldemo
numbers:
	python3 scripts/make_numbers.py
tooldemo:
	cd $@ && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
clean:
	cd tooldemo && latexmk -C
.PHONY: all numbers tooldemo clean
