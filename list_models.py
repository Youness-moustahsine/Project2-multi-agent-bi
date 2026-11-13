"""Affiche les modèles Groq disponibles avec ta clé : python list_models.py"""
from app.llm import LLM

for m in LLM().available_models():
    print(m)
