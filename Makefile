all: build

.PHONY: test

build: .build

.build: requirements.txt
	pip install -r requirements.txt
	touch .build

test: betabot
	nosetests betabot
	pyflakes betabot
	#pep8 --max-line-length=100 betabot
