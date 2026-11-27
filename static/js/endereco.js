/* Formulários de endereço (perfil), mapa do endereço e foto de perfil. */
document.addEventListener('DOMContentLoaded', () => {
  const sprite = document.body.dataset.sprite || '/static/icons/sprite.svg';
  const icon = (n) => `<svg class="icon icon-sm" aria-hidden="true"><use href="${sprite}#i-${n}"></use></svg>`;
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Preenchimento pelo CEP (ViaCEP via /api/cep).
  document.querySelectorAll('[data-address-form]').forEach((form) => {
    const cep = form.querySelector('[data-cep-lookup]');
    const feedback = form.querySelector('[data-cep-feedback]');
    const numero = form.querySelector('[data-numero]');
    const semNumero = form.querySelector('[data-sem-numero]');
    semNumero?.addEventListener('change', () => {
      numero.disabled = semNumero.checked;
      if (semNumero.checked) numero.value = '';
    });
    cep?.addEventListener('blur', async () => {
      const digits = cep.value.replace(/\D/g, '');
      if (digits.length !== 8) return;
      feedback.textContent = 'Consultando o CEP…';
      try {
        const response = await fetch(`/api/cep/${digits}`, { headers: { Accept: 'application/json' } });
        const data = await response.json();
        if (!response.ok) throw new Error(data.erro || 'CEP não encontrado.');
        const a = data.endereco;
        const set = (name, value) => {
          const field = form.querySelector(`[data-field="${name}"]`);
          if (!field || !value) return;
          field.value = value;
          field.dispatchEvent(new Event('change', { bubbles: true }));
          field.uiSync?.();
        };
        set('logradouro', a.logradouro); set('bairro', a.bairro); set('cidade', a.cidade); set('estado', a.estado);
        cep.removeAttribute('aria-invalid');
        feedback.textContent = 'Endereço encontrado. Confira e informe o número.';
        numero?.focus();
      } catch (error) {
        cep.setAttribute('aria-invalid', 'true');
        feedback.textContent = error.message;
      }
    });
  });

  // Mapa do endereço salvo (somente no perfil e no checkout).
  document.querySelectorAll('[data-map-toggle]').forEach((button) => button.addEventListener('click', async () => {
    const box = button.closest('.address-card').querySelector('[data-address-map]');
    if (!box.hidden && box.dataset.loaded) { box.hidden = true; return; }
    box.hidden = false;
    if (box.dataset.loaded) return;
    if (!box.dataset.ativo) {
      box.innerHTML = `<div class="map-mini-placeholder">${icon('map')}<span>Mapa indisponível: a integração com o Google Maps não está configurada.</span></div>`;
      box.dataset.loaded = '1';
      return;
    }
    box.innerHTML = '<div class="skeleton map-skeleton"></div>';
    const params = new URLSearchParams();
    if (box.dataset.numero) params.set('numero', box.dataset.numero);
    if (box.dataset.semNumero) params.set('sem_numero', '1');
    try {
      const response = await fetch(`/api/geo/${box.dataset.cep.replace(/\D/g, '')}?${params}`, { headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Não foi possível localizar.');
      if (!data.mapa) throw new Error(data.mapa_mensagem || 'Mapa indisponível.');
      box.innerHTML = `<iframe title="Mapa do endereço" src="${esc(data.mapa.embed_url)}" loading="lazy" referrerpolicy="no-referrer"></iframe><p class="map-legend ${data.mapa.preciso ? 'is-exact' : ''}">${icon(data.mapa.preciso ? 'crosshair' : 'map-pin')}${esc(data.mapa.legenda)}</p>${data.aviso ? `<p class="field-error">${icon('triangle-alert')}${esc(data.aviso)}</p>` : ''}`;
      box.dataset.loaded = '1';
    } catch (error) {
      box.innerHTML = `<div class="map-mini-placeholder">${icon('wifi-off')}<span>${esc(error.message)}</span></div>`;
    }
  }));

  // Prévia e validação da foto antes do envio (o servidor valida de novo).
  const input = document.querySelector('[data-avatar-input]');
  if (input) {
    const preview = document.querySelector('[data-avatar-preview]');
    const error = document.querySelector('[data-avatar-error]');
    const label = input.closest('.file-input')?.querySelector('span');
    input.addEventListener('change', () => {
      const file = input.files[0];
      error.hidden = true;
      if (!file) return;
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        error.textContent = 'Escolha uma imagem JPG, PNG ou WebP.'; error.hidden = false; input.value = ''; return;
      }
      if (file.size > 2 * 1024 * 1024) {
        error.textContent = 'A imagem deve ter no máximo 2 MB.'; error.hidden = false; input.value = ''; return;
      }
      if (label) label.textContent = file.name.length > 28 ? `${file.name.slice(0, 25)}…` : file.name;
      const url = URL.createObjectURL(file);
      preview.innerHTML = `<span class="avatar avatar-xl"><img src="${url}" alt="Prévia da nova foto"></span>`;
    });
  }
});
