# Release Engineering Assistant

A Python CLI chatbot with tool use and conversation memory, built with the Anthropic SDK and Claude Code for Costpoint release engineering tasks.

## Overview
An AI-powered assistant that automates cloud release engineering workflows through natural language — no manual lookups or script-switching required.

## Features
- Multi-turn conversation with session memory across follow-up questions
- Tool use: checks live EC2 instance states via AWS CLI
- Generates MR (Maintenance Release) deployment prep reports
- Context-aware responses based on conversation history

## Tools
- **EC2 State Checker** — queries AWS EC2 instance status by name pattern
- **MR Prep Generator** — produces structured deployment prep output from server lists

## Tech Stack
- Python
- Anthropic SDK (Claude API)
- AWS CLI / PowerShell
- Claude Code

## Usage
```bash
pip install -r requirements.txt
python assistant.py
