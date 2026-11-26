/* Validação inline no navegador (complementa a do servidor, que é a decisão final).
   Aplica-se a formulários com data-validate e a campos com regras conhecidas. */
(() => {
  'use strict';
  const DDDS = new Set([11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99]);
  const digits = (v) => String(v || '').replace(/\D/g, '');

  const regras = {
    cpf(valor) {
      const c = digits(valor);
      if (c.length !== 11 || /^(\d)\1+$/.test(c)) return 'Informe um CPF válido com 11 números.';
      for (const t of [9, 10]) {
        let soma = 0;
        for (let i = 0; i < t; i += 1) soma += Number(c[i]) * (t + 1 - i);
        let d = (soma * 10) % 11;
        if (d === 10) d = 0;
        if (d !== Number(c[t])) return 'CPF inválido: confira os dígitos.';
      }
      return '';
    },
    telefone(valor) {
      if (!valor.trim()) return '';
      const d = digits(valor);
      if (d.length !== 10 && d.length !== 11) return 'Informe DDD + número (10 ou 11 dígitos).';
      if (!DDDS.has(Number(d.slice(0, 2)))) return `O DDD ${d.slice(0, 2)} não existe.`;
      if (d.length === 11 && d[2] !== '9') return 'Celulares começam com 9 depois do DDD.';
      return '';
    },
    email(valor) {
      const e = valor.trim().toLowerCase();
      return /^(?!\.)(?!.*\.\.)[a-z0-9._%+-]+(?<!\.)@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$/.test(e) ? '' : 'Informe um e-mail válido, como nome@exemplo.com.';
    },
    nome(valor) {
      const n = valor.trim();
      if (n.length < 2) return 'O nome precisa ter pelo menos 2 caracteres.';
      if (/\d/.test(n)) return 'O nome não pode conter números.';
      return '';
    },
    nomeCompleto(valor) {
      const base = regras.nome(valor);
      if (base) return base;
      return valor.trim().split(/\s+/).filter((p) => p.length >= 2).length >= 2 ? '' : 'Informe nome e sobrenome.';
    },
    cep(valor) {
      return digits(valor).length === 8 ? '' : 'Informe um CEP com 8 números.';
    },
  };

  const regraDoCampo = (field) => {
    if (field.dataset.rule) return field.dataset.rule;
    if (field.hasAttribute('data-validate-nome')) return 'nome';
    if (field.hasAttribute('data-validate-telefone') || field.dataset.mask === 'phone') return 'telefone';
    if (field.dataset.mask === 'cpf') return 'cpf';
    if (field.dataset.mask === 'cep') return 'cep';
    if (field.type === 'email') return 'email';
    return null;
  };

  const errorEl = (field) => {
    const ids = (field.getAttribute('aria-describedby') || '').split(/\s+/);
    let el = ids.map((id) => id && document.getElementById(id)).find((n) => n && n.classList.contains('field-error'));
    if (!el) {
      el = document.createElement('p');
      el.className = 'field-error';
      el.id = `${field.id || field.name}-erro-js`;
      el.hidden = true;
      (field.closest('label, .field') || field).after(el);
      field.setAttribute('aria-describedby', `${field.getAttribute('aria-describedby') || ''} ${el.id}`.trim());
    }
    return el;
  };

  const mostrar = (field, mensagem) => {
    const el = errorEl(field);
    if (mensagem) {
      field.setAttribute('aria-invalid', 'true');
      el.textContent = mensagem;
      el.hidden = false;
    } else {
      field.removeAttribute('aria-invalid');
      el.hidden = true;
    }
  };

  const validar = (field) => {
    if (field.disabled || field.type === 'hidden') return true;
    let mensagem = '';
    if (field.required && !field.value.trim() && field.type !== 'checkbox') mensagem = 'Campo obrigatório.';
    else if (field.type === 'checkbox' && field.required && !field.checked) mensagem = 'Marque esta opção para continuar.';
    else if (field.value.trim()) {
      const regra = regraDoCampo(field);
      if (regra && regras[regra]) mensagem = regras[regra](field.value);
      if (!mensagem && field.minLength > 0 && field.value.length < field.minLength) mensagem = `Use pelo menos ${field.minLength} caracteres.`;
      if (!mensagem && field.dataset.match) {
        const outro = document.getElementById(field.dataset.match);
        if (outro && outro.value !== field.value) mensagem = 'As senhas não conferem.';
      }
    }
    mostrar(field, mensagem);
    return !mensagem;
  };

  window.BA = Object.assign(window.BA || {}, { validarCampo: validar, regras });

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form[data-validate]').forEach((form) => {
      const campos = () => [...form.querySelectorAll('input, textarea')].filter((f) => f.type !== 'hidden' && f.type !== 'file');
      campos().forEach((field) => {
        field.addEventListener('blur', () => { if (field.value || field.getAttribute('aria-invalid')) validar(field); });
        field.addEventListener('input', () => { if (field.getAttribute('aria-invalid')) validar(field); });
      });
      form.addEventListener('submit', (event) => {
        const invalidos = campos().filter((field) => !validar(field));
        if (invalidos.length) {
          event.preventDefault();
          event.stopImmediatePropagation();
          invalidos[0].focus();
        }
      }, true);
    });
  });
})();
