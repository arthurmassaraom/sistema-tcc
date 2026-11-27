document.addEventListener('DOMContentLoaded', () => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  document.querySelectorAll('form').forEach((form) => {
    if ((form.getAttribute('method') || 'get').toLowerCase() === 'post' && csrf && !form.querySelector('[name="_csrf_token"]')) {
      const token = document.createElement('input');
      token.type = 'hidden';
      token.name = '_csrf_token';
      token.value = csrf;
      form.appendChild(token);
    }
    form.addEventListener('submit', (event) => {
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
      }
    });
  });
  document.querySelectorAll('[data-mask]').forEach((field) => field.addEventListener('input', () => {
    let d = field.value.replace(/\D/g, '');
    if (field.dataset.mask === 'cep') {
      d = d.slice(0, 8);
      field.value = d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
    }
    if (field.dataset.mask === 'cpf') {
      d = d.slice(0, 11);
      field.value = d.replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    }
    if (field.dataset.mask === 'phone') {
      d = d.slice(0, 11);
      field.value = d.length > 10 ? d.replace(/(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3') : d.replace(/(\d{2})(\d{0,4})(\d{0,4})/, '($1) $2-$3');
    }
  }));
  // Formulários que se aplicam sozinhos ao mudar uma opção (ex.: entrega, ordenação).
  document.querySelectorAll('form[data-autosubmit]').forEach((form) => {
    form.addEventListener('change', () => (form.requestSubmit ? form.requestSubmit() : form.submit()));
  });
  // Menu da conta, gavetas e selects estilizados ficam em ui.js.
});
