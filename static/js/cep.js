/* Busca de bibliotecas por CEP (página Bibliotecas) e seleção de unidade no mapa. */
document.addEventListener('DOMContentLoaded', () => {
  const sprite = document.body.dataset.sprite || '/static/icons/sprite.svg';
  const icon = (name) => `<svg class="icon icon-sm" aria-hidden="true"><use href="${sprite}#i-${name}"></use></svg>`;
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Troca a unidade exibida no mapa sem recarregar a página.
  const frame = document.querySelector('[data-map-frame]');
  const caption = document.querySelector('[data-map-caption]');
  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-map-select]');
    if (!link || !frame || !link.dataset.mapUrl) return;
    event.preventDefault();
    frame.src = link.dataset.mapUrl;
    frame.title = `Mapa: ${link.dataset.mapName}`;
    if (caption) caption.innerHTML = `${icon('map-pin')}${esc(link.dataset.mapName)}`;
    document.querySelectorAll('.library-card').forEach((c) => c.classList.toggle('is-selected', c.contains(link)));
    if (window.matchMedia('(max-width: 1024px)').matches) document.getElementById('mapa')?.scrollIntoView({ behavior: 'smooth' });
  });

  const form = document.querySelector('#cep-form');
  if (!form) return;
  const input = document.querySelector('#cep');
  const feedback = document.querySelector('#cep-feedback');
  const result = document.querySelector('#cep-result');
  const container = document.querySelector('#regional-results');
  const skeleton = document.querySelector('#cep-skeleton');
  let controller = null;
  let requestId = 0;

  const setFeedback = (text, tone) => {
    feedback.textContent = text;
    feedback.dataset.tone = tone || '';
  };

  const card = (lib, highlight) => `
    <article class="library-card${highlight ? ' is-near' : ''}">
      <div class="library-card-head">
        <span class="badge ${highlight ? 'badge-success' : 'badge-primary'}">${icon(highlight ? 'navigation' : 'map-pin')}${esc(lib.badge || `${lib.estado} · ${lib.cidade}`)}</span>
        ${lib.horario ? `<span class="badge">${icon('clock')}${esc(lib.horario)}</span>` : ''}
      </div>
      <h3>${esc(lib.nome)}</h3>
      <p>${icon('map-pin')}${esc(lib.endereco)}, ${esc(lib.cidade)}/${esc(lib.estado)}</p>
      ${lib.cep || lib.telefone ? `<p>${icon('phone')}${esc([lib.cep ? `CEP ${lib.cep}` : '', lib.telefone].filter(Boolean).join(' · '))}</p>` : ''}
    </article>`;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const cep = input.value.replace(/\D/g, '');
    if (cep.length !== 8) {
      input.setAttribute('aria-invalid', 'true');
      setFeedback('Digite um CEP válido com 8 números.', 'error');
      input.focus();
      return;
    }
    input.removeAttribute('aria-invalid');
    setFeedback('Consultando endereço e bibliotecas próximas…', 'loading');
    container.innerHTML = skeleton ? skeleton.innerHTML : '';
    controller?.abort();
    controller = new AbortController();
    const current = ++requestId;
    try {
      const response = await fetch(`/api/cep/${cep}`, { headers: { Accept: 'application/json' }, signal: controller.signal });
      const data = await response.json().catch(() => ({}));
      if (current !== requestId) return;
      if (!response.ok) throw new Error(data.erro || 'Consulta indisponível no momento.');
      const a = data.endereco;
      result.hidden = false;
      result.className = 'cep-address';
      result.innerHTML = `${icon('map-pin')}<span><strong>CEP ${esc(a.cep || cep)}</strong> · ${esc(a.logradouro || 'logradouro não informado')} · ${esc(a.cidade)}/${esc(a.estado)}</span>`;
      const groups = [
        ['Na sua cidade', data.mesma_cidade, true],
        ['No seu estado', data.mesmo_estado, false],
        ['Outras regiões', data.outras_regioes, false],
      ];
      const total = groups.reduce((n, g) => n + g[1].length, 0);
      if (!total) {
        container.innerHTML = `<div class="empty-state is-compact"><span class="empty-state-icon">${icon('library')}</span><h3>Nenhuma unidade cadastrada ainda</h3><p>Você ainda pode receber os livros em casa escolhendo entrega no checkout.</p></div>`;
      } else {
        container.innerHTML = groups.filter((g) => g[1].length).map(([title, items, near]) => `
          <section class="library-group">
            <h2>${esc(title)} <span class="badge">${items.length}</span></h2>
            <div class="library-grid">${items.map((lib) => card(lib, near)).join('')}</div>
          </section>`).join('');
      }
      const near = data.mesma_cidade.length;
      setFeedback(near ? `Encontramos ${near} ${near === 1 ? 'unidade' : 'unidades'} na sua cidade.` : 'Nenhuma unidade na sua cidade; veja as mais próximas abaixo.', 'success');
    } catch (error) {
      if (error.name === 'AbortError' || current !== requestId) return;
      container.innerHTML = `<div class="empty-state is-compact is-error" role="alert"><span class="empty-state-icon">${icon('wifi-off')}</span><h3>Não foi possível buscar agora</h3><p>${esc(error.message)}</p><div class="button-row"><button class="button" type="button" data-cep-retry>${icon('refresh-cw')}Tentar de novo</button></div></div>`;
      setFeedback(error.message || 'Falha na consulta.', 'error');
    }
  });
  container.addEventListener('click', (event) => {
    if (event.target.closest('[data-cep-retry]')) form.requestSubmit();
  });
});
