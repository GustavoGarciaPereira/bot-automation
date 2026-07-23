"""Prompt templates for LLM classification by plugin."""

ML_CLASSIFY_PROMPT = """
Você é um classificador de produtos de e-commerce.
Classifique o produto abaixo.

Produto: {title}
Preço: R$ {price}

Responda APENAS em JSON válido:
{{
  "category": "categoria principal (ex: Informática, Celulares, Eletrônicos)",
  "subcategory": "subcategoria (ex: Notebooks, Smartphones, Tablets)",
  "brand": "marca (ex: Dell, Apple, Samsung)",
  "condition": "new ou used",
  "price_level": "barato, medio, caro, premium"
}}
"""

MAPS_CLASSIFY_PROMPT = """
Você é um classificador de empresas locais.
Classifique a empresa abaixo.

Empresa: {name}
Categoria: {category}
Endereço: {address}
Rating: {rating}

Responda APENAS em JSON válido:
{{
  "sector": "setor (ex: Saúde, Alimentação, Tecnologia, Educação)",
  "size": "pequeno, medio, grande",
  "lead_potential": "alto, medio, baixo",
  "lead_reason": "motivo em 1 frase"
}}
"""

OLX_CLASSIFY_PROMPT = """
Você é um classificador de anúncios de classificados.
Classifique o anúncio abaixo.

Título: {title}
Preço: R$ {price}
Localização: {location}

Responda APENAS em JSON válido:
{{
  "category": "categoria (ex: Informática, Veículos, Imóveis, Móveis)",
  "subcategory": "subcategoria (ex: Notebooks, Carros, Apartamentos)",
  "condition": "novo, seminovo, usado",
  "urgency": "urgente, normal",
  "price_level": "barato, medio, caro, premium"
}}
"""
