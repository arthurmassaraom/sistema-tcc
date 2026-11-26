/* ==========================================================================
   Biblioteca Aberta — componentes de interface
   - trapFocus: mantém o foco dentro de menus, gavetas e modais
   - Menu da conta (role="menu"): setas, Home/End, Esc, clique fora
   - Drawer (gaveta lateral): Esc, clique fora, fecha ao navegar, foco preso
   - Select estilizado: aprimora todo <select> nativo (padrão WAI-ARIA
     "select-only combobox"); o <select> original continua no formulário
   - Busca do cabeçalho: expansão no mobile e sugestões com teclado
   - Toast: mensagens temporárias anunciadas por aria-live
   Tudo é aprimoramento progressivo: sem JavaScript, links e formulários
   continuam funcionando.
   ========================================================================== */
(() => {
  'use strict';

  const FOCUSABLE = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
  ].join(',');

  const spriteUrl = () => document.body.dataset.sprite || '/static/icons/sprite.svg';

  const svgIcon = (name, extra = '') => {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', `icon ${extra}`.trim());
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const use = document.createElementNS(ns, 'use');
    use.setAttribute('href', `${spriteUrl()}#i-${name}`);
    svg.appendChild(use);
    return svg;
  };

  const isVisible = (el) => {
    if (!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)) return false;
    return getComputedStyle(el).visibility !== 'hidden';
  };

  const focusables = (root) => [...root.querySelectorAll(FOCUSABLE)]
    .filter((el) => isVisible(el) && !el.closest('[inert]') && !el.classList.contains('ui-select-native'));

  function trapFocus(container, event) {
    if (event.key !== 'Tab') return;
    const items = focusables(container);
    if (!items.length) {
      event.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const current = document.activeElement;
    if (event.shiftKey && (current === first || !container.contains(current))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (current === last || !container.contains(current))) {
      event.preventDefault();
      first.focus();
    }
  }

  /* ---------- Bloqueio de rolagem compartilhado ---------- */
  let lockCount = 0;
  const lockScroll = () => {
    lockCount += 1;
    document.body.classList.add('is-locked');
  };
  const unlockScroll = () => {
    lockCount = Math.max(0, lockCount - 1);
    if (!lockCount) document.body.classList.remove('is-locked');
  };

  /* ---------- Toast ---------- */
  function toast(message, { type = 'info', timeout = 4500 } = {}) {
    const region = document.getElementById('toast-region');
    if (!region) return;
    const item = document.createElement('div');
    item.className = `toast${type === 'error' ? ' is-error' : ''}`;
    item.setAttribute('role', type === 'error' ? 'alert' : 'status');
    item.appendChild(svgIcon(type === 'error' ? 'circle-alert' : type === 'success' ? 'circle-check' : 'info'));
    const text = document.createElement('span');
    text.textContent = message;
    item.appendChild(text);
    region.appendChild(item);
    setTimeout(() => item.remove(), timeout);
  }

  /* ---------- Gaveta (drawer) ---------- */
  const drawers = {};

  class Drawer {
    constructor(el) {
      this.el = el;
      this.trigger = null;
      this.isOpen = false;
      this.backdrop = document.createElement('div');
      this.backdrop.className = 'ui-backdrop';
      this.backdrop.hidden = true;
      el.before(this.backdrop);
      // data-drawer-media: só vira gaveta (modal) quando a media query casa.
      this.media = el.dataset.drawerMedia ? window.matchMedia(el.dataset.drawerMedia) : null;
      const applyMode = () => {
        const asDrawer = !this.media || this.media.matches;
        if (!asDrawer && this.isOpen) this.close({ restoreFocus: false });
        el.classList.toggle('is-static', !asDrawer);
        if (asDrawer) {
          el.setAttribute('role', 'dialog');
          el.setAttribute('aria-modal', 'true');
          el.setAttribute('aria-hidden', String(!this.isOpen));
        } else {
          el.removeAttribute('role');
          el.removeAttribute('aria-modal');
          el.removeAttribute('aria-hidden');
        }
      };
      this.media?.addEventListener?.('change', applyMode);
      applyMode();
      this.backdrop.addEventListener('click', () => this.close());
      el.addEventListener('keydown', (event) => {
        if (!this.isOpen) return;
        if (event.key === 'Escape') {
          event.stopPropagation();
          this.close();
        } else {
          trapFocus(el, event);
        }
      });
      el.addEventListener('click', (event) => {
        const closer = event.target.closest('[data-drawer-close]');
        if (closer) {
          event.preventDefault();
          this.close();
          return;
        }
        // Fecha ao navegar por um link da gaveta.
        const link = event.target.closest('a[href]');
        if (link && !link.getAttribute('href').startsWith('#') && !event.defaultPrevented) {
          this.close({ restoreFocus: false });
        }
      });
    }

    open(trigger = null) {
      if (this.isOpen) return;
      this.isOpen = true;
      this.trigger = trigger || document.activeElement;
      this.backdrop.hidden = false;
      this.el.setAttribute('aria-hidden', 'false');
      this.inertSiblings = [...document.body.children].filter((child) => (
        child !== this.el && child !== this.backdrop && child.id !== 'toast-region'
        && child.tagName !== 'SCRIPT' && !child.inert
      ));
      this.inertSiblings.forEach((child) => { child.inert = true; });
      lockScroll();
      document.querySelectorAll(`[aria-controls="${this.el.id}"]`).forEach((btn) => btn.setAttribute('aria-expanded', 'true'));
      requestAnimationFrame(() => {
        this.backdrop.classList.add('is-visible');
        this.el.classList.add('is-open');
        const title = this.el.querySelector('[data-drawer-title], h2[tabindex="-1"]');
        (title || focusables(this.el)[0] || this.el).focus({ preventScroll: true });
      });
      this.el.dispatchEvent(new CustomEvent('drawer:open', { bubbles: true }));
    }

    close({ restoreFocus = true } = {}) {
      if (!this.isOpen) return;
      this.isOpen = false;
      this.el.classList.remove('is-open');
      this.backdrop.classList.remove('is-visible');
      this.el.setAttribute('aria-hidden', 'true');
      (this.inertSiblings || []).forEach((child) => { child.inert = false; });
      this.inertSiblings = [];
      unlockScroll();
      document.querySelectorAll(`[aria-controls="${this.el.id}"]`).forEach((btn) => btn.setAttribute('aria-expanded', 'false'));
      const hide = () => { if (!this.isOpen) this.backdrop.hidden = true; };
      setTimeout(hide, 340);
      if (restoreFocus && this.trigger && document.contains(this.trigger)) this.trigger.focus({ preventScroll: true });
      this.el.dispatchEvent(new CustomEvent('drawer:close', { bubbles: true }));
    }
  }

  function initDrawers() {
    document.querySelectorAll('[data-drawer]').forEach((el) => {
      if (!el.id || drawers[el.id]) return;
      drawers[el.id] = new Drawer(el);
      if (location.hash === `#${el.id}`) {
        history.replaceState(null, '', location.pathname + location.search);
        drawers[el.id].open();
      }
    });
    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-drawer-open]');
      if (!trigger) return;
      const drawer = drawers[trigger.dataset.drawerOpen];
      if (!drawer) return;
      event.preventDefault();
      drawer.open(trigger);
    });
  }

  /* ---------- Menu suspenso (conta) ---------- */
  function initMenu(root) {
    const trigger = root.querySelector('[data-menu-trigger]');
    const panel = root.querySelector('[data-menu-panel]');
    if (!trigger || !panel) return;
    trigger.setAttribute('role', 'button');
    const items = () => [...panel.querySelectorAll('[role="menuitem"]')];
    const isOpen = () => !panel.hidden;
    const outside = (event) => {
      if (!root.contains(event.target)) close(false);
    };
    const open = (focusLast = false) => {
      panel.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      const list = items();
      (focusLast ? list[list.length - 1] : list[0])?.focus();
      document.addEventListener('pointerdown', outside, true);
    };
    function close(restore = true) {
      if (!isOpen()) return;
      panel.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      document.removeEventListener('pointerdown', outside, true);
      if (restore) trigger.focus();
    }
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      if (isOpen()) close();
      else open();
    });
    trigger.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' || event.key === ' ') {
        event.preventDefault();
        open();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        open(true);
      }
    });
    panel.addEventListener('keydown', (event) => {
      const list = items();
      const index = list.indexOf(document.activeElement);
      const move = (to) => {
        event.preventDefault();
        list[(to + list.length) % list.length]?.focus();
      };
      switch (event.key) {
        case 'ArrowDown': move(index + 1); break;
        case 'ArrowUp': move(index - 1); break;
        case 'Home': move(0); break;
        case 'End': move(list.length - 1); break;
        case 'Escape':
          event.preventDefault();
          event.stopPropagation();
          close();
          break;
        case 'Tab':
          trapFocus(panel, event);
          break;
        default:
          if (event.key.length === 1 && /\S/.test(event.key)) {
            const key = event.key.toLocaleLowerCase('pt-BR');
            const ordered = [...list.slice(index + 1), ...list.slice(0, index + 1)];
            ordered.find((item) => item.textContent.trim().toLocaleLowerCase('pt-BR').startsWith(key))?.focus();
          }
      }
    });
  }

  /* ---------- Select estilizado ---------- */
  let selectSequence = 0;
  const openSelects = new Set();

  function labelTextFor(select) {
    if (select.getAttribute('aria-label')) return select.getAttribute('aria-label');
    const label = select.closest('label') || (select.id && document.querySelector(`label[for="${CSS.escape(select.id)}"]`));
    if (!label) return '';
    let text = '';
    label.childNodes.forEach((node) => {
      if (node === select || (node.nodeType === 1 && node.contains(select))) return;
      text += node.textContent;
    });
    return text.replace(/\s+/g, ' ').trim();
  }

  function enhanceSelect(select) {
    if (select.dataset.enhanced || select.multiple || select.hasAttribute('data-native') || Number(select.size) > 1) return;
    select.dataset.enhanced = 'true';
    selectSequence += 1;
    const baseId = select.id || `ui-select-${selectSequence}`;
    const wrapper = document.createElement('div');
    wrapper.className = 'ui-select';
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    select.classList.add('ui-select-native');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    const combo = document.createElement('div');
    combo.className = 'ui-select-button';
    combo.id = `${baseId}-combo`;
    combo.setAttribute('role', 'combobox');
    combo.setAttribute('aria-haspopup', 'listbox');
    combo.setAttribute('aria-expanded', 'false');
    combo.setAttribute('aria-controls', `${baseId}-listbox`);
    const name = labelTextFor(select);
    if (name) combo.setAttribute('aria-label', name);
    if (select.required) combo.setAttribute('aria-required', 'true');
    const valueEl = document.createElement('span');
    valueEl.className = 'ui-select-value';
    combo.append(valueEl, svgIcon('chevron-down', 'ui-select-chevron icon-sm'));

    const list = document.createElement('ul');
    list.className = 'ui-select-list';
    list.id = `${baseId}-listbox`;
    list.setAttribute('role', 'listbox');
    if (name) list.setAttribute('aria-label', name);
    list.tabIndex = -1;
    list.hidden = true;
    wrapper.append(combo, list);

    // Quando o select está dentro de um <label>, clicar no combo faz o navegador
    // ativar o select nativo e abrir o menu sem estilo ao mesmo tempo.
    // Cancelamos essa ativação padrão; o menu estilizado continua funcionando.
    wrapper.addEventListener('click', (event) => event.preventDefault());

    let activeIndex = -1;
    let typed = '';
    let typedTimer = null;
    const options = () => [...select.options];

    const syncDisabled = () => {
      const disabled = select.disabled;
      combo.setAttribute('aria-disabled', String(disabled));
      combo.tabIndex = disabled ? -1 : 0;
      combo.classList.toggle('is-disabled', disabled);
      if (disabled) close(false);
    };

    const render = () => {
      const selected = select.options[select.selectedIndex];
      valueEl.textContent = selected ? selected.textContent.trim() : '';
      valueEl.classList.toggle('is-placeholder', !selected || selected.value === '');
    };

    const buildList = () => {
      list.replaceChildren();
      options().forEach((option, index) => {
        const item = document.createElement('li');
        item.className = 'ui-option';
        item.id = `${baseId}-opt-${index}`;
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(index === select.selectedIndex));
        if (option.disabled) item.setAttribute('aria-disabled', 'true');
        item.dataset.index = String(index);
        const label = document.createElement('span');
        label.textContent = option.textContent.trim();
        item.append(label, svgIcon('check', 'icon-sm'));
        list.appendChild(item);
      });
    };

    const setActive = (index, scroll = true) => {
      const items = [...list.children];
      if (!items.length) return;
      activeIndex = Math.max(0, Math.min(index, items.length - 1));
      items.forEach((item, i) => item.classList.toggle('is-active', i === activeIndex));
      combo.setAttribute('aria-activedescendant', items[activeIndex].id);
      if (scroll) items[activeIndex].scrollIntoView({ block: 'nearest' });
    };

    const step = (from, delta) => {
      const opts = options();
      let index = from;
      for (let i = 0; i < opts.length; i += 1) {
        index = Math.max(0, Math.min(index + delta, opts.length - 1));
        if (!opts[index].disabled) return index;
        if (index === 0 || index === opts.length - 1) break;
      }
      return from;
    };

    function open() {
      if (select.disabled || !list.hidden) return;
      openSelects.forEach((closeOther) => closeOther(false));
      buildList();
      list.hidden = false;
      wrapper.classList.add('is-open');
      const rect = combo.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom;
      wrapper.classList.toggle('opens-up', below < 240 && rect.top > below);
      combo.setAttribute('aria-expanded', 'true');
      setActive(select.selectedIndex >= 0 ? select.selectedIndex : 0);
      document.addEventListener('pointerdown', outside, true);
      openSelects.add(close);
    }

    function close(focus = true) {
      if (list.hidden) return;
      list.hidden = true;
      wrapper.classList.remove('is-open', 'opens-up');
      combo.setAttribute('aria-expanded', 'false');
      combo.removeAttribute('aria-activedescendant');
      document.removeEventListener('pointerdown', outside, true);
      openSelects.delete(close);
      if (focus) combo.focus();
    }

    function outside(event) {
      if (!wrapper.contains(event.target)) close(false);
    }

    const choose = (index) => {
      const option = select.options[index];
      if (!option || option.disabled) return;
      if (select.selectedIndex !== index) {
        select.selectedIndex = index;
        select.dispatchEvent(new Event('input', { bubbles: true }));
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      combo.removeAttribute('aria-invalid');
      render();
    };

    const typeAhead = (key) => {
      clearTimeout(typedTimer);
      typed += key.toLocaleLowerCase('pt-BR');
      typedTimer = setTimeout(() => { typed = ''; }, 600);
      const opts = options();
      const start = list.hidden ? select.selectedIndex : activeIndex;
      const ordered = [...opts.keys()].map((i) => (start + 1 + i) % opts.length);
      const match = ordered.find((i) => !opts[i].disabled && opts[i].textContent.trim().toLocaleLowerCase('pt-BR').startsWith(typed));
      if (match === undefined) return;
      if (list.hidden) choose(match);
      else setActive(match);
    };

    combo.addEventListener('click', () => {
      if (list.hidden) open();
      else close();
    });

    combo.addEventListener('keydown', (event) => {
      if (select.disabled) return;
      const isClosed = list.hidden;
      const { key } = event;
      if (isClosed) {
        if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(key)) {
          event.preventDefault();
          open();
        } else if (key === 'Home' || key === 'End') {
          event.preventDefault();
          open();
          setActive(key === 'Home' ? step(-1, 1) : step(select.options.length, -1));
        } else if (key.length === 1 && /\S/.test(key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
          typeAhead(key);
        }
        return;
      }
      switch (key) {
        case 'ArrowDown':
          event.preventDefault();
          if (event.altKey) { choose(activeIndex); close(); } else setActive(step(activeIndex, 1));
          break;
        case 'ArrowUp':
          event.preventDefault();
          if (event.altKey) { choose(activeIndex); close(); } else setActive(step(activeIndex, -1));
          break;
        case 'Home': event.preventDefault(); setActive(step(-1, 1)); break;
        case 'End': event.preventDefault(); setActive(step(select.options.length, -1)); break;
        case 'PageDown': event.preventDefault(); setActive(Math.min(activeIndex + 10, select.options.length - 1)); break;
        case 'PageUp': event.preventDefault(); setActive(Math.max(activeIndex - 10, 0)); break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          choose(activeIndex);
          close();
          break;
        case 'Escape':
          event.preventDefault();
          event.stopPropagation();
          close();
          break;
        case 'Tab':
          choose(activeIndex);
          close(false);
          break;
        default:
          if (key.length === 1 && /\S/.test(key)) typeAhead(key);
      }
    });

    combo.addEventListener('blur', (event) => {
      if (!wrapper.contains(event.relatedTarget)) close(false);
    });

    list.addEventListener('pointerdown', (event) => event.preventDefault());
    list.addEventListener('click', (event) => {
      const item = event.target.closest('.ui-option');
      if (!item || item.getAttribute('aria-disabled') === 'true') return;
      choose(Number(item.dataset.index));
      close();
    });
    list.addEventListener('pointermove', (event) => {
      const item = event.target.closest('.ui-option');
      if (item) setActive(Number(item.dataset.index), false);
    });

    // O <select> nativo continua sendo a fonte da verdade do formulário.
    select.addEventListener('focus', () => combo.focus());
    select.addEventListener('change', () => { render(); combo.removeAttribute('aria-invalid'); });
    select.addEventListener('invalid', () => {
      combo.setAttribute('aria-invalid', 'true');
      combo.focus();
    });
    select.form?.addEventListener('reset', () => setTimeout(render));
    new MutationObserver(() => {
      syncDisabled();
      if (select.required) combo.setAttribute('aria-required', 'true');
      else combo.removeAttribute('aria-required');
      render();
    }).observe(select, { attributes: true, attributeFilter: ['disabled', 'required'], childList: true, subtree: true });

    select.uiSync = render;
    syncDisabled();
    render();
  }

  const enhanceSelects = (root = document) => {
    root.querySelectorAll('select').forEach(enhanceSelect);
  };

  /* ---------- Busca com sugestões ---------- */
  const fold = (text) => [...text].map((c) => {
    const base = c.normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR');
    return base.length === 1 ? base : c.toLocaleLowerCase('pt-BR');
  }).join('');

  function highlight(text, query) {
    const fragment = document.createDocumentFragment();
    const index = fold(text).indexOf(fold(query));
    if (index < 0 || !query) {
      fragment.append(text);
      return fragment;
    }
    const mark = document.createElement('mark');
    mark.textContent = text.slice(index, index + query.length);
    fragment.append(text.slice(0, index), mark, text.slice(index + query.length));
    return fragment;
  }

  function initSearch(form) {
    const header = form.closest('[data-site-header]');
    const input = form.querySelector('input[name="q"]');
    const listbox = form.querySelector('[role="listbox"]');
    const status = form.querySelector('[data-search-status]');
    const openButton = document.querySelector('[data-search-open]');
    const closeButton = form.querySelector('[data-search-close]');
    const endpoint = form.dataset.suggestUrl;
    const mobile = window.matchMedia('(max-width: 768px)');
    if (!input || !listbox) return;

    let timer = null;
    let controller = null;
    let active = -1;
    let lastQuery = '';

    const optionEls = () => [...listbox.querySelectorAll('[role="option"]')];

    const hideList = () => {
      listbox.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      active = -1;
    };

    const showList = () => {
      listbox.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    };

    const setActive = (index) => {
      const items = optionEls();
      if (!items.length) return;
      active = (index + items.length) % items.length;
      items.forEach((item, i) => {
        item.classList.toggle('is-active', i === active);
        item.setAttribute('aria-selected', String(i === active));
      });
      input.setAttribute('aria-activedescendant', items[active].id);
      items[active].scrollIntoView({ block: 'nearest' });
    };

    const openMobile = () => {
      header.classList.add('is-search-open');
      openButton?.setAttribute('aria-expanded', 'true');
      input.focus();
    };

    const closeMobile = (restore = true) => {
      if (!header.classList.contains('is-search-open')) return;
      header.classList.remove('is-search-open');
      openButton?.setAttribute('aria-expanded', 'false');
      hideList();
      if (restore) openButton?.focus();
    };

    openButton?.addEventListener('click', (event) => {
      if (!mobile.matches) return;
      event.preventDefault();
      openMobile();
    });
    closeButton?.addEventListener('click', () => closeMobile());
    mobile.addEventListener?.('change', () => closeMobile(false));

    const makeOption = (id, href, thumb, title, subtitle, badge) => {
      const option = document.createElement('div');
      option.className = 'suggest-option';
      option.id = id;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      option.dataset.href = href;
      option.append(thumb);
      const text = document.createElement('span');
      text.className = 'suggest-text';
      const strong = document.createElement('strong');
      strong.append(title);
      text.append(strong);
      if (subtitle) {
        const small = document.createElement('span');
        small.append(subtitle);
        text.append(small);
      }
      option.append(text);
      if (badge) option.append(badge);
      return option;
    };

    const groupLabel = (text, id) => {
      const label = document.createElement('div');
      label.className = 'suggest-group-label';
      label.id = id;
      label.setAttribute('role', 'presentation');
      label.textContent = text;
      return label;
    };

    const catalogUrl = (q) => `${form.action}?q=${encodeURIComponent(q)}`;

    const footerOption = (q) => {
      const thumb = document.createElement('span');
      thumb.className = 'suggest-thumb is-author';
      thumb.append(svgIcon('search', 'icon-sm'));
      const option = makeOption('sugestao-busca', catalogUrl(q), thumb, `Buscar “${q}” no acervo`, '', null);
      option.classList.add('suggest-footer');
      return option;
    };

    const renderLoading = () => {
      listbox.replaceChildren();
      for (let i = 0; i < 3; i += 1) {
        const row = document.createElement('div');
        row.className = 'suggest-skeleton';
        row.setAttribute('aria-hidden', 'true');
        const cover = document.createElement('span');
        cover.className = 'skeleton';
        const lines = document.createElement('div');
        lines.innerHTML = '<span class="skeleton skeleton-text" style="display:block;width:70%"></span><span class="skeleton skeleton-text is-short" style="display:block"></span>';
        row.append(cover, lines);
        listbox.append(row);
      }
      showList();
    };

    const renderResults = (data, q) => {
      listbox.replaceChildren();
      let count = 0;
      if (data.livros.length) {
        listbox.append(groupLabel('Livros', 'sugestoes-livros'));
        data.livros.forEach((livro, i) => {
          const thumb = document.createElement('span');
          thumb.className = 'suggest-thumb';
          if (livro.capa) {
            const img = document.createElement('img');
            img.src = livro.capa;
            img.alt = '';
            img.loading = 'lazy';
            thumb.append(img);
          } else {
            thumb.append(svgIcon('book', 'icon-sm'));
          }
          let badge = null;
          if (!livro.disponivel) {
            badge = document.createElement('span');
            badge.className = 'badge badge-warning';
            badge.textContent = 'Indisponível';
          }
          listbox.append(makeOption(`sugestao-livro-${i}`, livro.url, thumb, highlight(livro.titulo, q), highlight(livro.autor, q), badge));
          count += 1;
        });
      }
      if (data.autores.length) {
        listbox.append(groupLabel('Autores', 'sugestoes-autores'));
        data.autores.forEach((autor, i) => {
          const thumb = document.createElement('span');
          thumb.className = 'suggest-thumb is-author';
          thumb.append(svgIcon('user', 'icon-sm'));
          listbox.append(makeOption(`sugestao-autor-${i}`, autor.url, thumb, highlight(autor.nome, q), 'Ver obras deste autor', null));
          count += 1;
        });
      }
      if (!count) {
        const empty = document.createElement('div');
        empty.className = 'suggest-empty';
        empty.setAttribute('role', 'presentation');
        empty.append(svgIcon('search-x'));
        const text = document.createElement('span');
        text.textContent = `Nenhum título ou autor começa com “${q}”. Tente outro termo ou busque no acervo completo.`;
        empty.append(text);
        listbox.append(empty);
      }
      listbox.append(footerOption(q));
      showList();
      if (status) status.textContent = count ? `${count} ${count === 1 ? 'sugestão disponível' : 'sugestões disponíveis'}.` : 'Nenhuma sugestão encontrada.';
    };

    const renderError = (q) => {
      listbox.replaceChildren();
      const error = document.createElement('div');
      error.className = 'suggest-empty';
      error.setAttribute('role', 'presentation');
      error.append(svgIcon('wifi-off'));
      const text = document.createElement('span');
      text.textContent = 'Não foi possível carregar sugestões agora. Pressione Enter para buscar mesmo assim.';
      error.append(text);
      listbox.append(error, footerOption(q));
      showList();
    };

    const fetchSuggestions = async (q) => {
      controller?.abort();
      controller = new AbortController();
      renderLoading();
      try {
        const response = await fetch(`${endpoint}?q=${encodeURIComponent(q)}`, {
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error('falha');
        const data = await response.json();
        if (q !== lastQuery) return;
        renderResults(data, q);
      } catch (error) {
        if (error.name !== 'AbortError' && q === lastQuery) renderError(q);
      }
    };

    input.addEventListener('input', () => {
      const q = input.value.replace(/\s+/g, ' ').trim();
      lastQuery = q;
      clearTimeout(timer);
      active = -1;
      input.removeAttribute('aria-activedescendant');
      if (q.length < 2 || !endpoint) {
        controller?.abort();
        hideList();
        return;
      }
      timer = setTimeout(() => fetchSuggestions(q), 180);
    });

    input.addEventListener('keydown', (event) => {
      const items = optionEls();
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (listbox.hidden && lastQuery.length >= 2) fetchSuggestions(lastQuery);
        else setActive(active + 1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        if (!listbox.hidden) setActive(active - 1);
      } else if (event.key === 'Enter' && !listbox.hidden && active >= 0 && items[active]) {
        event.preventDefault();
        window.location.href = items[active].dataset.href;
      } else if (event.key === 'Escape') {
        event.stopPropagation();
        if (!listbox.hidden) {
          event.preventDefault();
          hideList();
        } else if (header.classList.contains('is-search-open')) {
          event.preventDefault();
          closeMobile();
        } else if (input.value) {
          input.value = '';
        }
      }
    });

    listbox.addEventListener('pointerdown', (event) => event.preventDefault());
    listbox.addEventListener('click', (event) => {
      const option = event.target.closest('[role="option"]');
      if (option) window.location.href = option.dataset.href;
    });

    form.addEventListener('focusout', (event) => {
      if (form.contains(event.relatedTarget)) return;
      setTimeout(() => {
        if (form.contains(document.activeElement)) return;
        hideList();
        if (mobile.matches) closeMobile(false);
      }, 120);
    });

    form.addEventListener('submit', (event) => {
      if (!input.value.trim()) {
        event.preventDefault();
        input.focus();
      }
    });
  }

  /* ---------- Abas (role=tablist) ---------- */
  function initTabs(root) {
    const tabs = [...root.querySelectorAll('[role="tab"]')];
    if (!tabs.length) return;
    const select = (tab, focus = true) => {
      tabs.forEach((item) => {
        const active = item === tab;
        item.setAttribute('aria-selected', String(active));
        item.tabIndex = active ? 0 : -1;
        const panel = document.getElementById(item.getAttribute('aria-controls'));
        if (panel) panel.hidden = !active;
      });
      if (focus) tab.focus();
      if (root.dataset.tabsParam && tab.dataset.tab) {
        const url = new URL(window.location.href);
        url.searchParams.set(root.dataset.tabsParam, tab.dataset.tab);
        url.hash = '';
        history.replaceState(null, '', url);
      }
      root.dispatchEvent(new CustomEvent('tabs:change', { detail: { tab: tab.dataset.tab } }));
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', (event) => {
        event.preventDefault();
        select(tab, false);
      });
      tab.addEventListener('keydown', (event) => {
        const keys = { ArrowRight: index + 1, ArrowDown: index + 1, ArrowLeft: index - 1, ArrowUp: index - 1, Home: 0, End: tabs.length - 1 };
        if (!(event.key in keys)) return;
        event.preventDefault();
        select(tabs[(keys[event.key] + tabs.length) % tabs.length]);
      });
    });
    // Abre a aba indicada pelo #hash (ex.: /login#cadastro).
    const fromHash = tabs.find((tab) => location.hash && tab.getAttribute('aria-controls') === location.hash.slice(1));
    if (fromHash) select(fromHash, false);
  }

  /* ---------- Modal de confirmação ---------- */
  function confirmar(mensagem, { confirmar: textoOk = 'Confirmar', perigo = true } = {}) {
    return new Promise((resolve) => {
      const anterior = document.activeElement;
      const backdrop = document.createElement('div');
      backdrop.className = 'ui-backdrop is-visible';
      const modal = document.createElement('div');
      modal.className = 'ui-modal';
      modal.setAttribute('role', 'alertdialog');
      modal.setAttribute('aria-modal', 'true');
      modal.setAttribute('aria-labelledby', 'modal-titulo');
      modal.setAttribute('aria-describedby', 'modal-texto');
      modal.innerHTML = '<h2 id="modal-titulo">Tem certeza?</h2><p id="modal-texto"></p><div class="button-row"></div>';
      modal.querySelector('#modal-texto').textContent = mensagem;
      const cancelar = document.createElement('button');
      cancelar.type = 'button';
      cancelar.className = 'button button-light';
      cancelar.textContent = 'Cancelar';
      const ok = document.createElement('button');
      ok.type = 'button';
      ok.className = `button ${perigo ? 'button-danger' : ''}`;
      ok.textContent = textoOk;
      modal.querySelector('.button-row').append(cancelar, ok);
      document.body.append(backdrop, modal);
      lockScroll();
      const fechar = (resultado) => {
        backdrop.remove();
        modal.remove();
        unlockScroll();
        anterior?.focus?.();
        resolve(resultado);
      };
      cancelar.addEventListener('click', () => fechar(false));
      ok.addEventListener('click', () => fechar(true));
      backdrop.addEventListener('click', () => fechar(false));
      modal.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') { event.preventDefault(); fechar(false); } else trapFocus(modal, event);
      });
      cancelar.focus();
    });
  }

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm || form.dataset.confirmed) return;
    event.preventDefault();
    if (await confirmar(form.dataset.confirm)) {
      form.dataset.confirmed = '1';
      form.requestSubmit ? form.requestSubmit() : form.submit();
    }
  });

  /* ---------- Contador da sacola ---------- */
  function setCartCount(count) {
    const total = Math.max(0, Number(count) || 0);
    document.querySelectorAll('[data-cart-count]').forEach((badge) => {
      const changed = badge.textContent.trim() !== String(total);
      badge.textContent = String(total);
      badge.classList.toggle('is-empty', total === 0);
      if (changed && badge.classList.contains('cart-count')) {
        badge.classList.remove('is-bumped');
        void badge.offsetWidth;
        badge.classList.add('is-bumped');
      }
    });
    document.querySelectorAll('[data-cart-trigger]').forEach((trigger) => {
      trigger.setAttribute('aria-label', `Sacola, ${total} ${total === 1 ? 'item' : 'itens'}`);
    });
  }

  window.BA = Object.assign(window.BA || {}, {
    trapFocus, focusables, toast, confirmar, drawers, Drawer, enhanceSelect, enhanceSelects, setCartCount, svgIcon, lockScroll, unlockScroll,
  });

  document.addEventListener('DOMContentLoaded', () => {
    initDrawers();
    document.querySelectorAll('[data-menu]').forEach(initMenu);
    document.querySelectorAll('[data-search]').forEach(initSearch);
    document.querySelectorAll('[data-tabs]').forEach(initTabs);
    enhanceSelects();
  });
})();
