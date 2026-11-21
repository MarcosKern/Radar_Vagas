# Radar de Vagas

> **Versão atual: V0.1** · Projeto em desenvolvimento (pré-1.0)

Aplicação para centralizar oportunidades de emprego, auxiliar na análise de aderência às vagas e gerar currículos personalizados, legíveis por sistemas ATS (*Applicant Tracking Systems*).

## Objetivo

Reduzir o trabalho manual de encontrar, comparar e acompanhar oportunidades, mantendo um currículo-base verdadeiro e gerando versões adequadas aos requisitos de cada vaga, em português ou inglês.

## Funcionalidades planejadas

- **Oportunidades:** busca e listagem de vagas, com cards e links para a publicação original.
- **Busca com IA:** indicadores de pesquisa, andamento e resultado, com mensagens descartáveis e feedback explícito de sucesso/erro.
- **Aderência à vaga:** comparação transparente entre requisitos da vaga e experiências/competências informadas pelo candidato.
- **Currículos ATS-friendly:** modelo de coluna única, seções tradicionais e texto selecionável, sem inventar experiências ou competências.
- **Personalização:** escolha de idioma (PT-BR ou EN), ajustes de layout e configuração de currículo-base.
- **Geração por vaga:** ação fixa dentro de cada card de oportunidade para gerar/baixar o currículo contextualizado.
- **Histórico:** área de histórico acessível pelo menu.
- **Versões:** convenção `V0.X` até a preparação da versão `V1.0`.

> **Estado de implementação:** este repositório começa como estrutura de documentação e templates. Busca automatizada, IA, geração de arquivos e interface ainda não foram implementadas neste pacote inicial.

## Estrutura

```text
Radar_Vagas/
├── .github/ISSUE_TEMPLATE/   # Modelos de issues
├── backend/                  # Código do backend (a definir)
├── frontend/                 # Código da interface (a definir)
├── docs/                     # Requisitos e diretrizes ATS
├── templates/                # Bases editáveis de currículo (PT/EN)
├── .editorconfig
├── .gitignore
└── README.md                  # Visão geral e changelog único
```

## Requisitos de qualidade

- Currículos sempre editáveis e com conteúdo verificável.
- Não prometer aprovação automática nem apresentar “pontuação ATS” como medida universal.
- Feedback claro de carregamento, falha, conclusão e encerramento de notificações.
- Testes de interpretação e extração de texto de documentos exportados.
- Respeito à privacidade dos dados do candidato; não publicar currículos pessoais no repositório.

## Desenvolvimento

A stack ainda não foi definida nesta base. Os diretórios `frontend/` e `backend/` estão reservados para implementação futura. Consulte [`docs/REQUISITOS.md`](docs/REQUISITOS.md) e [`docs/ATS.md`](docs/ATS.md).

## Changelog

Todas as alterações são documentadas **neste único README.md**, da versão mais recente para a mais antiga.

### V0.1 — 21/11/2026

- Estrutura inicial do projeto e documentação do escopo.
- Diretrizes de compatibilidade com ATS.
- Modelos editáveis de currículo em português e inglês.
- Publicação inicial no GitHub.

## Licença

Nenhuma licença de código aberto foi escolhida. A disponibilização pública do repositório não concede, por si só, uma licença de reutilização do código.
