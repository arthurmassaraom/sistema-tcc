/* ==========================================================================
   Sacola em painel lateral
   - Abre pelo ícone da sacola (data-drawer-open="sacola"), sem trocar de página
   - Atualiza e remove itens via fetch + JSON nos endpoints existentes
     (carrinho.atualizar / carrinho.remover) com o token no cabeçalho X-CSRF-Token
   - Anuncia mudanças por aria-live
   - Sem JavaScript, /carrinho continua funcionando normalmente
   ========================================================================== */
(() => {
  'use strict';

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
  const money = (n) => Number(n || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  document.addEventListener('DOMContentLoaded', () => {
    const drawerEl = document.querySelector('[data-cart-drawer]');
    if (!drawerEl || !window.BA) return;
    const sprite = document.body.dataset.sprite || '/static/icons/sprite.svg';
    const icon = (name, cls = '') => `<svg class="icon ${cls}" aria-hidden="true" focusable="false"><use href="${sprite}#i-${name}"></use></svg>`;
    const body = drawerEl.querySelector('[data-cart-body]');
    const live = drawerEl.querySelector('[data-cart-live]');
    const heading = drawerEl.querySelector('[data-cart-heading]');
    const subtotalEl = drawerEl.querySelector('[data-cart-subtotal]');
    const freteEl = drawerEl.querySelector('[data-cart-frete]');
    const totalEl = drawerEl.querySelector('[data-cart-total]');
    const checkoutBtn = drawerEl.querySelector('[data-cart-checkout]');
    const deliveryRadios = [...drawerEl.querySelectorAll('[data-cart-delivery] input')];
    const urls = drawerEl.dataset;
    let state = null;
    let busy = false;

    const announce = (message) => {
      live.textContent = '';
      setTimeout(() => { live.textContent = message; }, 40);
    };

    const request = async (url, payload) => {
      const options = {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      };
      if (payload) {
        options.method = 'POST';
        options.headers['Content-Type'] = 'application/json';
        options.headers['X-CSRF-Token'] = csrf();
        options.body = JSON.stringify(payload);
      }
      const response = await fetch(url, options);
      let data = null;
      try { data = await response.json(); } catch (_) { data = null; }
      if (!data) throw new Error('Não foi possível falar com o servidor. Verifique sua conexão e tente novamente.');
      return { response, data };
    };

    const labelTipo = (item) => (item.tipo === 'aluguel'
      ? `<span class="badge badge-info">${icon('clock')}Aluguel · ${item.dias} dias</span>`
      : `<span class="badge badge-accent">${icon('bookmark')}Compra</span>`);

    const coverHtml = (capa, titulo) => (capa
      ? `<img src="${esc(capa)}" alt="" width="64" height="96" loading="lazy" decoding="async">`
      : `<span class="cover-fallback is-mini" aria-hidden="true"><strong>${esc(titulo)}</strong></span>`);

    const renderSuggestions = (items) => {
      if (!items?.length) return '';
      return `
        <section class="cart-suggestions" aria-labelledby="sacola-sugestoes">
          <h3 id="sacola-sugestoes">${icon('sparkles', 'icon-sm')}Que tal começar por aqui?</h3>
          <ul>
            ${items.map((s) => `
              <li class="cart-suggestion">
                <a class="cart-item-cover" href="${esc(s.url)}" tabindex="-1" aria-hidden="true">${coverHtml(s.capa, s.titulo)}</a>
                <div class="cart-suggestion-text">
                  <a href="${esc(s.url)}"><strong>${esc(s.titulo)}</strong></a>
                  <span>${esc(s.autor)}</span>
                  <span class="cart-suggestion-price">${s.tipo === 'aluguel' ? 'Aluguel a partir de ' : ''}${money(s.preco)}</span>
                </div>
                <button class="button button-light button-small" type="button" data-suggest-add="${s.livro_id}" data-tipo="${esc(s.tipo)}" aria-label="Adicionar ${esc(s.titulo)} à sacola">${icon('plus', 'icon-sm')}</button>
              </li>`).join('')}
          </ul>
        </section>`;
    };

    const render = (data) => {
      state = data;
      body.setAttribute('aria-busy', 'false');
      const count = data.quantidade_total || 0;
      window.BA.setCartCount(count);
      heading.textContent = `${count} ${count === 1 ? 'item' : 'itens'}`;
      if (!data.itens.length) {
        body.innerHTML = `
          <div class="empty-state is-compact cart-empty">
            <span class="empty-state-icon">${icon('shopping-bag')}</span>
            <h3>Sua sacola está esperando uma história</h3>
            <p>Escolha um livro para alugar ou comprar. Ele fica guardado aqui enquanto você navega.</p>
            <div class="button-row"><a class="button" href="/livros">${icon('book-open')}Explorar o acervo</a></div>
          </div>
          ${renderSuggestions(data.sugestoes)}`;
      } else {
        body.innerHTML = `
          <ul class="cart-items" aria-label="Itens na sacola">
            ${data.itens.map((item) => `
              <li class="cart-item" data-key="${esc(item.key)}">
                <a class="cart-item-cover" href="${esc(item.url)}" tabindex="-1" aria-hidden="true">${coverHtml(item.capa, item.titulo)}</a>
                <div class="cart-item-main">
                  <div class="cart-item-head">
                    <div>
                      <a class="cart-item-title" href="${esc(item.url)}">${esc(item.titulo)}</a>
                      <p class="cart-item-author">${esc(item.autor)}</p>
                    </div>
                    <button class="cart-item-remove" type="button" data-remove aria-label="Remover ${esc(item.titulo)} da sacola">${icon('trash-2')}</button>
                  </div>
                  ${labelTipo(item)}
                  <div class="cart-item-foot">
                    <div class="stepper" role="group" aria-label="Quantidade de ${esc(item.titulo)}">
                      <button type="button" data-step="-1" aria-label="Diminuir quantidade"${item.quantidade <= 1 ? ' disabled' : ''}>${icon('minus', 'icon-sm')}</button>
                      <input type="number" inputmode="numeric" min="1" max="${item.maximo}" value="${item.quantidade}" aria-label="Quantidade" data-qty>
                      <button type="button" data-step="1" aria-label="Aumentar quantidade"${item.quantidade >= item.maximo ? ' disabled' : ''}>${icon('plus', 'icon-sm')}</button>
                    </div>
                    <div class="cart-item-price">
                      <strong>${money(item.subtotal)}</strong>
                      ${item.quantidade > 1 ? `<small>${money(item.unitario)} cada</small>` : ''}
                    </div>
                  </div>
                </div>
              </li>`).join('')}
          </ul>
          ${renderSuggestions(data.sugestoes)}`;
      }
      subtotalEl.textContent = money(data.subtotal);
      if (data.entrega === 'domicilio') freteEl.textContent = money(data.frete_domicilio);
      else if (data.entrega === 'retirada') freteEl.textContent = 'Grátis';
      else freteEl.textContent = 'Escolha acima';
      totalEl.textContent = money(data.total);
      deliveryRadios.forEach((radio) => {
        radio.checked = radio.value === data.entrega;
        radio.disabled = !data.itens.length;
      });
      checkoutBtn.disabled = !data.itens.length;
      drawerEl.querySelector('[data-cart-footer]').classList.toggle('is-empty', !data.itens.length);
      checkoutBtn.setAttribute('aria-describedby', data.itens.length ? '' : 'sacola-vazia-dica');
    };

    const renderError = (message) => {
      body.setAttribute('aria-busy', 'false');
      body.innerHTML = `
        <div class="empty-state is-compact is-error" role="alert">
          <span class="empty-state-icon">${icon('wifi-off')}</span>
          <h3>Não conseguimos carregar sua sacola</h3>
          <p>${esc(message)}</p>
          <div class="button-row">
            <button class="button" type="button" data-cart-retry>${icon('refresh-cw')}Tentar de novo</button>
            <a class="button button-light" href="/carrinho">Abrir a página da sacola</a>
          </div>
        </div>`;
    };

    const load = async () => {
      body.setAttribute('aria-busy', 'true');
      try {
        const { data } = await request(urls.stateUrl);
        render(data);
      } catch (error) {
        renderError(error.message);
      }
    };

    const mutate = async (url, payload, successMessage) => {
      if (busy) return;
      busy = true;
      body.setAttribute('aria-busy', 'true');
      drawerEl.classList.add('is-busy');
      try {
        const { response, data } = await request(url, payload);
        render(data);
        if (!response.ok || data.ok === false) {
          announce(data.mensagem || 'Não foi possível atualizar a sacola.');
          window.BA.toast(data.mensagem || 'Não foi possível atualizar a sacola.', { type: 'error' });
        } else if (successMessage) {
          announce(successMessage(data));
        }
      } catch (error) {
        announce(error.message);
        window.BA.toast(error.message, { type: 'error' });
      } finally {
        busy = false;
        drawerEl.classList.remove('is-busy');
        body.setAttribute('aria-busy', 'false');
      }
    };

    const itemTitle = (key) => state?.itens.find((i) => i.key === key)?.titulo || 'Item';

    const updateQty = (key, qty) => {
      const titulo = itemTitle(key);
      mutate(urls.updateUrl, { key, quantidade: qty }, (data) => {
        const item = data.itens.find((i) => i.key === key);
        return item ? `Quantidade de ${titulo} atualizada para ${item.quantidade}. Subtotal ${money(data.subtotal)}.` : `${titulo} removido da sacola.`;
      }).then(() => {
        drawerEl.querySelector(`.cart-item[data-key="${CSS.escape(key)}"] [data-qty]`)?.focus();
      });
    };

    body.addEventListener('click', (event) => {
      const retry = event.target.closest('[data-cart-retry]');
      if (retry) { load(); return; }
      const suggest = event.target.closest('[data-suggest-add]');
      if (suggest) {
        mutate(urls.addUrl, { livro_id: suggest.dataset.suggestAdd, tipo: suggest.dataset.tipo, dias: 14, quantidade: 1 },
          (data) => data.mensagem || 'Livro adicionado à sacola.');
        return;
      }
      const row = event.target.closest('.cart-item[data-key]');
      if (!row) return;
      const key = row.dataset.key;
      if (event.target.closest('[data-remove]')) {
        const titulo = itemTitle(key);
        mutate(urls.removeUrl, { key }, () => `${titulo} foi removido da sacola.`).then(() => {
          (drawerEl.querySelector('.cart-item-remove') || drawerEl.querySelector('#sacola-titulo'))?.focus();
        });
        return;
      }
      const step = event.target.closest('[data-step]');
      if (step) {
        const input = row.querySelector('[data-qty]');
        const next = Math.max(1, Math.min(Number(input.max), Number(input.value) + Number(step.dataset.step)));
        if (next !== Number(input.value)) updateQty(key, next);
      }
    });

    body.addEventListener('change', (event) => {
      const input = event.target.closest('[data-qty]');
      if (!input) return;
      const row = input.closest('.cart-item');
      const value = Math.round(Number(input.value));
      if (!Number.isFinite(value) || value < 1) {
        input.value = state?.itens.find((i) => i.key === row.dataset.key)?.quantidade || 1;
        return;
      }
      updateQty(row.dataset.key, Math.min(value, Number(input.max)));
    });

    deliveryRadios.forEach((radio) => radio.addEventListener('change', () => {
      mutate(urls.deliveryUrl, { modo: radio.value }, (data) => (data.entrega === 'domicilio'
        ? `Entrega em domicílio selecionada. Total ${money(data.total)}.`
        : `Retirada gratuita selecionada. Total ${money(data.total)}.`));
    }));

    checkoutBtn.addEventListener('click', () => {
      if (!checkoutBtn.disabled) window.location.href = checkoutBtn.dataset.href;
    });

    drawerEl.addEventListener('drawer:open', load);

    // Formulários "Adicionar à sacola": envio por JSON e abertura do painel.
    document.addEventListener('submit', async (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      const action = new URL(form.action, window.location.href);
      if (action.pathname !== new URL(urls.addUrl, window.location.href).pathname) return;
      if (!form.checkValidity()) return;
      event.preventDefault();
      const payload = {};
      new FormData(form).forEach((value, key) => { if (key !== '_csrf_token') payload[key] = value; });
      const button = form.querySelector('[type="submit"]');
      button?.setAttribute('aria-busy', 'true');
      if (button) button.disabled = true;
      try {
        const { response, data } = await request(urls.addUrl, payload);
        if (!response.ok || data.ok === false) {
          window.BA.toast(data.mensagem || 'Não foi possível adicionar o livro.', { type: 'error' });
          return;
        }
        window.BA.drawers.sacola?.open(document.querySelector('[data-cart-trigger]'));
        render(data);
        announce(data.mensagem || 'Livro adicionado à sacola.');
        window.BA.toast(data.mensagem || 'Livro adicionado à sacola.', { type: 'success' });
      } catch (error) {
        // Em último caso, envia o formulário normalmente.
        form.submit();
      } finally {
        button?.removeAttribute('aria-busy');
        if (button) button.disabled = false;
      }
    });
  });
})();
