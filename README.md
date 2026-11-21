# Radar de Vagas — V0.16
> **Instalação inicial:** este projeto não inclui `config.json`, bancos SQLite, vagas, candidaturas,
> perfis profissionais, credenciais ou arquivos de exemplo. Na primeira execução, o sistema
> usa apenas valores técnicos mínimos em memória, com todas as fontes desativadas.
> Para restaurar as preferências use **Configurações → Backup JSON → Importar configurações**;
> para restaurar suas vagas use **Importar XLSX/CSV**. Nenhuma informação pessoal é preenchida automaticamente.
> Arquivos `config.json` e `data/jobs.sqlite` serão criados localmente quando você salvar
> preferências ou iniciar/importar dados. **Extraia em uma pasta nova**, sem mesclar com
> uma instalação anterior que ainda tenha seus dados.


Sistema local de monitoramento e organização de oportunidades de TI para Windows, com painel responsivo, importação/exportação de vagas, acompanhamento de candidaturas e geração de currículos personalizáveis por vaga.

**Versão atual:** V0.16 (pré-lançamento). A numeração de desenvolvimento segue `V0.X` até a primeira versão estável. **Toda a documentação e todo o histórico de versões ficam neste único `README.md`**. Não são criados arquivos `CHANGELOG_*.md` separadamente.

## Instalação e uso rápido

No Windows x64, extraia o ZIP inteiro e abra o atalho **Radar de Vagas** (`.lnk`) na raiz da pasta extraída. Ele inicia `Projeto\Radar de Vagas.exe`, que usa o código e o Python incluídos em `Projeto`. O servidor roda em segundo plano e abre o painel no navegador. Mova a pasta extraída inteira para manter o destino do atalho acessível. As configurações, vagas e atualizações da instalação desktop ficam em `%LOCALAPPDATA%\RadarDeVagas`. Para migrar da distribuição anterior, feche o servidor e copie seu `config.json` e a pasta `data` para esse diretório antes da primeira abertura.

Para executar pelo código-fonte:

1. Instale **Python 3.11 ou superior** no Windows e habilite a opção *Add Python to PATH*.
2. Extraia o pacote completo para uma nova pasta (por exemplo, `Documentos\Radar_de_vagas`).
3. Execute `abrir_painel.bat` e abra `http://127.0.0.1:8765/`, caso a página não seja exibida automaticamente.
4. Na instalação limpa, abra **Fontes e filtros → Backup JSON** e importe seu arquivo de configurações. Caso não tenha backup, configure manualmente as fontes, termos e dados do currículo.
5. Use **Importar XLSX/CSV** para restaurar vagas e candidaturas. Depois de habilitar fontes, clique em **Buscar vagas** para uma nova coleta.
6. Use **Oportunidades**, **Candidaturas**, **Bloqueados** e **Fontes e filtros** para gerenciar o trabalho.

A interface e o banco de dados SQLite funcionam localmente; coletas externas precisam de conexão de internet. Tailwind, Bootstrap e CSS customizado já estão incluídos. O aplicativo **não envia candidaturas automaticamente** aos sites das empresas. Registrar candidatura significa registrar no Radar uma inscrição realizada externamente.

## Funcionalidades principais

- **Oportunidades:** fontes públicas e ATS configuráveis, combinação de termos, classificação de aderência, links dos anúncios, bloqueios manuais e exclusões automáticas por senioridade.
- **Candidaturas:** controle de status e contatos, histórico de movimentações com data/hora, anotações, datas de acompanhamento e filtros recolhíveis. O Radar permite registrar uma candidatura, avançar etapas e registrar rejeição mediante confirmação.
- **Monitor de buscas:** etapas, fontes, erros e métricas de execução coletadas pelo backend, incluindo motivos de descarte automático.
- **Currículos:** modelos Word editáveis em português e inglês, adaptados aos requisitos da vaga somente com dados profissionais declarados, incluindo editor de layout e prévia aproximada.
- **Excel:** importação e exportação XLSX com abas `Candidaturas` e `Detalhes das vagas`; colunas adicionais são opcionais e o arquivo legado continua aceito.
- **Aparência:** nomes, títulos e ordem dos itens do menu personalizáveis, mantendo as seções obrigatórias acessíveis.

## Configurações e exclusões

O menu **Fontes e filtros** organiza as configurações em: Regras, Exclusões, Fontes, Termos, IA, Currículo e Aparência. Os títulos dessas seções seguem um padrão visual uniforme, sem numeração. A navegação é lateral no desktop e responsiva em telas menores.

Em **Exclusões**, as categorias Sênior, Pleno, Lead, Staff, Gerente e Arquiteto são bloqueadas por padrão, enquanto Júnior e Estágio permanecem permitidos. É possível acrescentar até 40 expressões e testar títulos antes de salvar. As regras são aplicadas ao **nível da vaga**, considerando título, senioridade informada e indicações explícitas na descrição; o nome de empresas como **Senior Sistemas** não deve gerar descarte. O monitor diferencia exclusões automáticas de vagas **Bloqueadas** manualmente.

## Acompanhamento de candidaturas

A seção **Candidaturas** contabiliza vagas em Candidatada, Triagem, Entrevista, Teste técnico, Proposta, Aprovada ou Rejeitada. A lista prioriza por padrão as etapas mais avançadas, com outros critérios disponíveis nos filtros. Os filtros iniciam recolhidos e podem ser expandidos por botão.

Cada candidatura tem botões para **Gerenciar**, **Avançar etapa** e **Registrar rejeição**; mudanças rápidas pedem confirmação. Dentro de **Gerenciar**, o histórico é uma linha do tempo de leitura, separado das anotações. Eventos registram data/hora e origem; salvar o mesmo status ou alterar somente notas não produz mudança de etapa fictícia. Não são inventadas datas de movimentos anteriores à implementação do histórico.

## Currículos por vaga

Abra **Fontes e filtros → Currículo** para cadastrar e revisar dados profissionais, resumos PT/EN, experiências, competências, idiomas, formação, certificações e projetos. No personalizador, altere estilo, A4/Carta, margens, fonte, tamanhos, entrelinha, espaçamento, alinhamento e ordem das seções.

O botão **Currículo** fica **fixo no rodapé dos cards**, sem acompanhar o cursor e sem brilho externo. Ao acioná-lo, escolha **Português** ou **English** e baixe um `.docx`. O gerador reordena somente experiências e competências presentes no perfil e relevantes à vaga; não inventa qualificações. A prévia HTML é ilustrativa e pode diferir da paginação do Word. O formato é de coluna única, sem foto e sem tabela, mas nenhuma estrutura garante aprovação em ATS.

## Busca com IA na nuvem

A consulta opcional usa a **API Google Gemini**, sem instalar Ollama ou modelos locais. Obtenha sua chave em https://aistudio.google.com/apikey, configure-a na aba **IA** e use **Testar conexão**. O seletor trabalha com uma lista de modelos candidatos à modalidade gratuita e consulta a disponibilidade permitida para sua chave; a visibilidade de um modelo não garante quota ou permissão para gerar conteúdo.

A IA amplia combinações de cargos e competências; os anúncios são recuperados dos conectores públicos, que podem falhar ou ter limites. Google Search Grounding permanece desligado no backend para evitar operações faturáveis nessa configuração. Erros de quota (429), rede, permissão ou modelo indisponível devem ser observados no monitor. Os limites reais e preços podem mudar; consulte https://ai.google.dev/gemini-api/docs/pricing antes de usar. Nunca compartilhe `data/gemini.key`.

## Fontes de vagas

- **Brasil e agregadores:** Gupy (endpoint público não oficial), Adzuna (requer chaves próprias) e Arbeitnow.
- **Remotas internacionais:** Himalayas, Jobicy, Remotive, Remote OK e We Work Remotely.
- **ATS por empresa:** Greenhouse, Lever, Ashby, SmartRecruiters, Workable e Recruitee, exigindo configuração de empresas/boards.

As fontes não garantem cobertura completa ou disponibilidade permanente. O histórico registra indisponibilidades, timeouts, falhas HTTP e resultados de coleta. Anúncios devem ser confirmados no site original.

## Importação/exportação de vagas e configurações

**Importar vagas** aceita XLSX (duas abas `Candidaturas` e `Detalhes das vagas`) e CSV (UTF-8 ou Windows-1252; `;` ou `,`). Apenas cargo e empresa são obrigatórios; colunas adicionais são opcionais. Vagas **Nova** com ID da vaga são restauradas. Registros com status **explicitamente Nova** sem ID são ignorados, para que a importação de uma lista de oportunidades não crie candidaturas indevidas. Sem coluna de status, o cadastro ainda pode ser importado como oportunidade Nova. Duplicatas são atualizadas sem apagar anotações, nem retroceder etapas avançadas.

**Exportar vagas** abre filtros independentes da página: escopo (somente candidaturas por padrão, todas, ativas, salvas, bloqueadas), status, empresa, modalidade, pesquisa textual, período e tipo de data, incluir/ocultar bloqueadas. A quantidade é calculada pelo backend antes de baixar; **a mesma seleção** é exportada em **CSV ou XLSX**, incluindo candidaturas encerradas e de vagas bloqueadas se habilitado. O filtro padrão *Somente candidaturas* exclui vagas Nova ou apenas Salva. Para incluir todas as oportunidades, selecione *Todas as vagas* explicitamente.

**Exportar configurações (JSON):** em **Configurações → Backup JSON**, baixe ou importe um arquivo com fontes, filtros, menus, aparência e layout/dados do currículo. O arquivo contém versão de esquema e é validado integralmente antes da importação; **não** inclui histórico/banco de vagas nem chave Gemini. O JSON pode conter dados pessoais preenchidos no currículo e deve ser mantido privado.

**Baixar template:** o botão **Modelo XLSX** no topo do painel fornece a planilha em branco para novos cadastros.

## Atualização sem perda de dados

1. Feche o aplicativo anterior e faça backup de **toda a pasta `data/`**, principalmente `data/jobs.sqlite`.
2. Guarde uma cópia de `config.json` para consultar suas personalizações. **Evite substituir por completo** um arquivo atual usando um `config.json` muito antigo, pois novas configurações podem ter sido adicionadas.
3. Extraia a nova versão em outra pasta; copie o banco antigo para `data/jobs.sqlite` da nova instalação, com as duas instalações fechadas.
4. Reaplique suas preferências de fontes, busca, visual e currículo conforme necessário.
5. Abra `abrir_painel.bat` e confira candidaturas, bloqueados e histórico.

Não compartilhe bancos, chaves de API nem arquivos de configuração com dados pessoais. O pacote distribuído não deve conter bancos de demonstração ou credenciais.

## Execução técnica e testes

```bash
python monitor.py serve
python monitor.py scan
python -m unittest discover -s tests -v
```

Para gerar um executável Windows x64, instale Go 1.24+ no ambiente de build e rode `python desktop/build.py --manifest` e `python desktop/build.py --package Radar_de_Vagas_V0.16.zip`. O build verifica o SHA-256 do Python embarcado. Para publicar uma atualização da aplicação, incremente a versão, atualize este histórico, gere o manifesto e integre os arquivos juntos na `main`. Mudanças no próprio inicializador ou no Python embarcado exigem uma nova distribuição do executável.

O servidor web opera em `127.0.0.1`; a busca periódica pode ser agendada com `agendar_buscas.ps1`. Os registros de busca são armazenados localmente. A coleta depende de acesso de rede e da disponibilidade dos provedores.

---

## Histórico de versões

Registros em **ordem cronológica, da versão mais antiga para a mais recente**. As identificações históricas foram normalizadas para o padrão de pré-lançamento `V0.X`. Algumas versões antigas foram distribuídas com nomenclatura `v1`, `v3.0` etc.; os resumos delas foram recuperados dos respectivos `README.md` presentes nos pacotes. As notas detalhadas a partir de V0.8 foram incorporadas dos antigos arquivos de changelog. **A V0.10 e a antiga v10.0 eram o mesmo conteúdo: somente uma entrada foi mantida.**

### V0.1 — base inicial (antigo v1)

- Primeiro monitor de vagas com banco SQLite, pontuação explicável de aderência, deduplicação, acompanhamento de status e exportação CSV.
- Coleta em fontes públicas, dashboard web local e inicializadores Windows.

### V0.3 — renovação visual e cadastro manual (antiga v3.0)

- Interface responsiva baseada em Tailwind, Bootstrap e CSS próprio.
- Inclusão manual de vagas, bloqueio persistente de oportunidades ignoradas e reativação, sem apagar anotações.

### V0.4 — configurações e Excel (antiga v4.0)

- Correção dos botões de cadastro e gerenciamento, com edição de status, notas e acompanhamento.
- Fontes organizadas por grupo, termos inseridos como cards, combinações limitadas de pesquisa e integração opcional com IA.
- Importação/exportação XLSX em duas abas e tolerância a colunas opcionais; layout com cantos mais quadrados.

### V0.5 — candidaturas e monitoramento (antiga v5.0)

- Seção **Bloqueados** com contador e reativação; contador e filtros específicos de **Candidaturas**.
- Personalização dos nomes e da ordem dos menus, títulos de páginas e acesso rápido à busca com IA.
- Ajuste de board inválido do Recruitee e integração opcional com Ollama local (substituída na V0.6).

### V0.6 — IA na nuvem (antiga v6.0)

- Substituição do Ollama por API Gemini com chave configurada no painel, sem instalar modelos locais.
- Botões para salvar/remover a chave, testar a conexão e pesquisar com IA; limites diários e atenção ao custo.

### V0.7 — modelos e logs de buscas (antiga v7.0)

- Lista de modelos restrita a opções com modalidade gratuita documentada, validada conforme acesso da chave.
- Monitor de execução com logs reais do backend, etapas, progresso e classificação de falhas e limites de uso da API.

### V0.8 — exclusões configuráveis (antiga v8.0)

## Inclusões

- **Configurações → Exclusões**: categorias Sênior, Pleno, Lead, Staff, Gerente e Arquiteto ativas por padrão; Estágio e Júnior desligadas por padrão.
- Até 40 termos de exclusão personalizados, inseridos via Enter ou botão, e removidos como cards.
- **Teste de exclusão** com prévia antes de salvar.
- Comparação de termos por palavras inteiras, com reconhecimento de termos em português e inglês.
- Aplicação dos filtros antes do cálculo de aderência em **Buscar vagas** e **Buscar com IA**.
- Descrições são examinadas somente quando informam explicitamente o nível da posição. Menções a colegas seniores não removem automaticamente vagas júnior.
- **Monitor de buscas** apresenta descartes automáticos separadamente de bloqueios manuais, com exemplos e motivos registrados em `data/executions.json`.
- Configurações divididas em seis abas: Regras, Exclusões, Fontes, Termos, IA e Aparência.
- Layout mais organizado e angular, com campos alinhados, espaçamento revisado e comportamento responsivo.

## Preservado

- Cadastro manual, bloqueios persistentes, candidatura e anotações, gestão de status, personalização de menus, importação/exportação XLSX, 14 conectores configuráveis, API Gemini na nuvem e histórico de buscas.
- Os descartes automáticos **não apagam** candidaturas existentes nem entram em **Bloqueados**. Alterar o filtro afeta futuras coletas, não reprocessa anúncios históricos automaticamente.

## Instalação e migração

1. Feche a versão anterior e faça backup da pasta `data/`.
2. Extraia a v8 em pasta nova.
3. Copie seu banco anterior `data/jobs.sqlite` para a pasta `data/` da v8, com os aplicativos fechados.
4. Se necessário, configure novamente sua chave Gemini. Não compartilhe `data/gemini.key`.
5. Execute `abrir_painel.bat`.
6. Em **Fontes e filtros → Exclusões**, ajuste as categorias e clique em **Salvar preferências**.

**Compatibilidade:** o banco SQLite é mantido. É recomendável reaplicar personalizações de fontes e menus pelo painel, em vez de sobrescrever o `config.json` novo com um arquivo antigo.

## Validação

- **83 testes automatizados** em Python passaram.
- UI interativa validada no navegador com chamadas da API simuladas; sem erros JavaScript e sem overflow horizontal em telas de 390px.
- Rotas locais de teste de exclusão validadas por HTTP.
- Acesso do navegador automatizado ao servidor `127.0.0.1` foi bloqueado pelo ambiente de testes; uma busca externa real não foi executada nesta revisão.

### V0.8.1 — menu lateral nas configurações (antiga v8.1)

- Navegação entre abas movida para um menu lateral no desktop e layout adaptado para celular.
- Botão de atualização de modelos Gemini alinhado ao texto explicativo.

### V0.8.2 — menu sem numeração (antiga v8.2)

- Removida a numeração do menu lateral de configurações, preservando os nomes e controles.

### V0.9 — candidaturas e identidade visual (antiga v9.0)

- Corrigida a rota do favicon e substituída a identificação principal para **Radar de vagas**.
- Candidaturas ordenáveis por etapa, filtros recolhíveis e ações rápidas de avanço/rejeição com confirmação.
- Ajustes de alinhamento nos controles da IA em nuvem.

### V0.9.1 — filtros, links e senioridade (antiga v9.1)

## Oportunidades
- O painel de filtros de oportunidades volta a conter todos os filtros clássicos: pesquisa, modalidade, etapa, fonte, visualização, ordenação e ocultação de vagas tratadas.
- O painel completo inicia recolhido e abre/fecha ao clicar em **Explorar oportunidades**. Um contador sinaliza filtros ativos mesmo quando recolhido.
- Todos os cards exibem o link da vaga em texto e o botão **Abrir vaga** (somente URLs HTTP/HTTPS); quando não há link, o sistema informa isso e desabilita o botão.
- O botão **Registrar candidatura** abre confirmação explícita e, ao confirmar, marca o status `Candidatada`, preenche a data da primeira candidatura e mantém a vaga no Radar. Não envia inscrição ao site da empresa.
- A opção só fica habilitada em vagas `Nova` ou `Salva` que não estejam bloqueadas.

## Exclusões e senioridade
- A classificação considera título, campo de senioridade e menções **explícitas ao nível do cargo** na descrição, sem usar o nome da empresa como indicação de senioridade.
- Em títulos com a empresa anexada, o nome completo da empresa é removido da interpretação de nível, incluindo variações com sufixos societários.
- Trechos sobre colegas/mentores de maior senioridade não excluem automaticamente vagas júnior.
- O preview de filtros agora aceita **Empresa (opcional)**, para reproduzir casos como **Senior Sistemas**.
- O cálculo de pontuação não penaliza nomes de empresas que contenham palavras como `Senior`.
- Mantidos os controles anteriores de exclusões configuráveis, além dos bloqueios manuais separados.

## Compatibilidade e testes
- Mantidas as rotas, o esquema de banco e a importação/exportação XLSX existentes.
- 93 testes automatizados passaram; teste funcional no navegador executado sem acesso à internet, com respostas simuladas.
- Uma execução real de busca externa depende da disponibilidade das APIs no computador do usuário.

## Atualização
1. Faça backup de `data/jobs.sqlite` no aplicativo antigo.
2. Extraia esta versão em uma **nova pasta**.
3. Copie o banco anterior para `data/jobs.sqlite` na nova instalação.
4. Execute `abrir_painel.bat` e confirme as candidaturas existentes.

### V0.9.2 — histórico de movimentações (antiga v9.2)

- Nova tabela SQLite `job_status_history`, criada automaticamente sem remover dados existentes.
- Registro transacional de eventos de mudança de status, com data/hora e origem.
- Eventos automáticos no cadastro manual, edição, importação XLSX e atualizações na aba Candidaturas.
- Novo endpoint somente leitura `GET /api/jobs/{id}/history`, com retorno de eventos da vaga específica.
- Painel de linha do tempo dentro do modal **Gerenciar candidatura**, separado das anotações livres.
- Estados inicial, sem eventos e falha de carregamento tratados explicitamente.
- Sem eventos duplicados ao salvar o mesmo status ou modificar apenas notas.
- Histórico removido somente quando um cadastro manual é excluído definitivamente.
- Eventos prévios à atualização não recebem datas fabricadas.
- 102 testes automatizados aprovados.

## Segurança e compatibilidade

A integração não altera o formato do XLSX nem os critérios de coleta. Preserve `data/jobs.sqlite` ao atualizar.

### V0.10 — currículos personalizados (antiga v10.0)

- Novo botão flutuante **✦ Currículo** em cada card, com efeito de iluminação que acompanha o cursor; botão fixo alternativo para touch/teclado.
- Modal para escolha de português ou inglês, prévia das habilidades correspondentes e download DOCX individual por vaga.
- Seção **Currículo** nas configurações para editar perfil, experiências, competências, educação, certificações, projetos, contato e estrutura visual.
- Geração DOCX sem bibliotecas externas, sem chave Gemini e sem inserção de qualificações inexistentes.
- Templates genéricos PT/EN disponíveis na pasta `templates/` e no painel.
- Back-end atualizado com novas rotas `/api/resume/docx`, `/api/resume/template`, `/api/resume/match`.
- Configuração persistida em `config.json`; compatibilidade com arquivos anteriores e SQLite preservada.
- Navegação lateral de configurações continua sem numeração.
- 114 testes automatizados passaram; fluxos visuais testados com respostas de API simuladas.

### V0.11 — personalizador de layout

- Botão Currículo permanece fixo no card, com interação interna discreta e sem brilho externo.
- Editor visual de layout: estilo, tamanho de página, margens, fonte, tamanhos, espaçamentos, alinhamento e ordem das seções.
- Prévia ilustrativa em português ou inglês, atualizada enquanto o usuário edita o perfil.
- Word gerado respeita as escolhas salvas; não há alteração nas experiências declaradas.
- Compatibilidade com as configurações das versões anteriores, com valores padrão para os novos campos.

**Nota:** A prévia HTML é aproximada. A paginação pode mudar no Word conforme a fonte e o tamanho do conteúdo.

### V0.12 — padronização dos títulos

- Removida a numeração de todos os títulos e cabeçalhos de Configurações.
- Padronizados título, descrição, cor, fonte, peso, alinhamento, divisor e espaçamento das sete abas: Regras, Exclusões, Fontes, Termos, IA, Currículo e Aparência.
- Removida a numeração também da lista de personalização dos itens de menu.
- Mantidas todas as IDs e as ações ligadas aos controles existentes; nenhuma alteração nos modelos, filtros ou banco de dados.

### V0.13 — documentação consolidada

- Todos os antigos arquivos `CHANGELOG_*.md` foram incorporados a este `README.md`, em ordem cronológica e sem duplicações.
- Histórico de versões anteriores recuperado dos pacotes disponíveis, com notas técnicas completas preservadas onde existiam arquivos de changelog.
- Instruções atuais de instalação, migração, IA, currículo e candidaturas foram organizadas em seções de referência únicas, eliminando chamadas a arquivos de changelog que não existirão mais.
- Nenhuma alteração no formato do banco de dados, nas regras de busca ou no funcionamento das candidaturas.


### V0.14 — filtros de exportação e backup JSON

- Janela própria de exportação com filtros de escopo, status, empresa, modalidade, busca textual, período e inclusão de bloqueadas, além de prévia de quantidade.
- Exportação padrão de **somente candidaturas**, inclusive etapas concluídas/rejeitadas; exportação de todas as vagas somente quando escolhida.
- CSV e XLSX gerados pela **mesma seleção do backend**, independentemente dos filtros temporários do painel de oportunidades.
- Importação também por CSV, com reconhecimento de cabeçalhos simples, colunas opcionais e deduplicação. Registros com status explicitamente `Nova` não são importados; registros sem coluna de status continuam permitidos.
- Reimportação preserva notas e evita rebaixar candidaturas que já avançaram para etapas posteriores.
- Backup de configurações em JSON versionado para importar/exportar fontes, regras, menus, aparência e currículo sem copiar o banco ou a chave Gemini.
- O filtro de oportunidades aplica as exclusões de senioridade às oportunidades já armazenadas (sem apagar candidaturas) e reduz anúncios duplicados entre conectores.


### V0.15 — executável Windows e atualizações

- Executável Windows x64 com Python incluído, servidor em segundo plano e abertura do painel no navegador.
- Verificação do repositório na abertura, com opção de instalar ou adiar. A aba Atualizações permite consultar novamente e ler o histórico.
- Atualizações de aplicação usam o manifesto publicado na main, baixam arquivos alterados, conferem SHA-256 e reiniciam o servidor. As versões ficam separadas dos dados. Se a candidata falhar na inicialização, o supervisor volta à anterior.
- Restauração de oportunidades Nova exportadas com ID em CSV e XLSX. Filtros de oportunidades e exportação de vagas ativas tratam duplicatas entre fontes.

### V0.16 — alinhamento dos indicadores de busca

- Centralizados os símbolos dentro dos indicadores circulares das etapas do monitor de busca, sem alterar cores, tamanhos ou o restante do painel.
