'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const el = id => document.getElementById(id);
  const dialog = el('updateDialog');
  let token, target, applying = false;
  async function request(action, method = 'GET') {
    const response = await fetch('/api/updates' + action, {
      method, cache: 'no-store', headers: token ? {'X-Radar-Token': token} : {}
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Falha ao consultar atualizações.');
    return data;
  }
  function display(data) {
    target = data.latest;
    el('updateStatus').textContent = 'Instalada ' + data.installed + '. ' + data.message +
      (target ? ' Versão disponível ' + target + '.' : '');
    el('applyUpdate').hidden = !(target && data.managed);
    el('releaseHistory').replaceChildren(...data.history.map(record => {
      const section = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = record.version + ' · ' + record.title;
      const list = document.createElement('ul');
      for (const change of record.changes) {
        const item = document.createElement('li');
        item.textContent = change.replace(/\*\*|`/g, '');
        list.append(item);
      }
      section.append(summary, list);
      return section;
    }));
  }
  async function check(prompt) {
    el('checkUpdates').disabled = true;
    try {
      const local = await request('');
      token = local.token;
      display(local);
      el('updateStatus').textContent = 'Instalada ' + local.installed + '. Verificando atualizações…';
      const result = await request('/check', 'POST');
      display(result);
      if (prompt && target && result.managed) {
        el('updateDescription').textContent = 'A versão ' + target + ' está disponível. O Radar baixará os arquivos alterados e reiniciará o servidor.';
        dialog.showModal();
      }
    } catch (error) { el('updateStatus').textContent = error.message; }
    finally { el('checkUpdates').disabled = false; }
  }
  async function apply() {
    if (applying) return;
    applying = true;
    const expected = target;
    if (!dialog.open) dialog.showModal();
    const buttons = ['confirmUpdate','applyUpdate','deferUpdate','checkUpdates'].map(el);
    buttons.forEach(b => b.disabled = true);
    try {
      el('updateDescription').textContent = 'Baixando e verificando os arquivos alterados…';
      await request('/apply', 'POST');
      el('updateDescription').textContent = 'Reiniciando o Radar…';
      for (let i = 0; i < 60; i++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        try {
          const health = await request('/health');
          if (health.version === expected) { location.reload(); return; }
        } catch { /* Servidor em reinicialização. */ }
      }
      throw Error('A nova versão não confirmou a inicialização. Reabra o Radar para conferir a versão ativa.');
    } catch (error) {
      el('updateStatus').textContent = el('updateDescription').textContent = error.message;
    } finally {
      applying = false;
      buttons.forEach(b => b.disabled = false);
    }
  }
  dialog.addEventListener('cancel', event => { if (applying) event.preventDefault(); });
  el('deferUpdate').addEventListener('click', () => dialog.close());
  el('checkUpdates').addEventListener('click', () => check(false));
  el('applyUpdate').addEventListener('click', apply);
  el('confirmUpdate').addEventListener('click', apply);
  check(true);
});
