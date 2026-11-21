# Requisitos — Radar de Vagas (V0.1)

## Funcionais

- **RF01 — Cadastro do currículo-base:** permitir informar formação, experiências, competências, idiomas e links profissionais.
- **RF02 — Busca de vagas:** oferecer pesquisa com filtros e apresentar a origem de cada oportunidade.
- **RF03 — Estados de carregamento:** indicar busca iniciada, busca em andamento, sucesso, resultado vazio e falha.
- **RF04 — Cards de oportunidades:** exibir informações essenciais, URL original e ação fixa para gerar currículo adaptado.
- **RF05 — Comparação com vaga:** destacar correspondências, lacunas e evidências verificáveis do currículo-base.
- **RF06 — Geração de currículo:** criar documento contextualizado para uma vaga sem inventar experiências ou certificações.
- **RF07 — Idiomas:** permitir exportar em português e inglês, respeitando traduções corretas de cargos e termos.
- **RF08 — Personalização de layout:** controlar fonte, espaçamento e seções sem comprometer a leitura por ATS.
- **RF09 — Histórico:** armazenar consultas, oportunidades salvas e versões de currículo com acesso via menu.
- **RF10 — Notificações:** apresentar mensagens com ação explícita de fechar (`X`).

## Não funcionais

- **RNF01:** interface responsiva e acessível, incluindo uso por teclado.
- **RNF02:** exportações em formato legível por máquinas, com texto selecionável.
- **RNF03:** transparência sobre dados ausentes e origem de vagas.
- **RNF04:** tratamento de erros e feedback de sucesso em operações demoradas.
- **RNF05:** minimização e proteção de dados pessoais.
- **RNF06:** testes automatizados do processamento, geração e leitura de arquivos.

## Critérios de aceitação iniciais

- A ação de gerar currículo fica **dentro do card**, sem acompanhar o cursor.
- O hover afeta apenas a área interna do botão, sem efeito de brilho externo.
- Títulos de configurações seguem o mesmo padrão, sem numeração.
- Histórico aparece no menu principal.
- Mensagens podem ser fechadas e estados de erro não são reportados como sucesso.
- O `README.md` mantém o changelog centralizado em ordem de versões.

## Pendente de decisão

- Framework de frontend, backend e banco de dados.
- Fontes e métodos autorizados de busca de vagas.
- Serviço de IA, custos e estratégia de proteção de dados.
- Formatos definitivos de exportação (DOCX, PDF).
