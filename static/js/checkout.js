document.addEventListener('DOMContentLoaded', () => {
  const app = document.querySelector('#checkout-app');
  const form = document.querySelector('#checkout-details-form');
  if (!app || !form) return;
  const address = document.querySelector('#delivery-address');
  const pickup = document.querySelector('#pickup-library');
  const freight = document.querySelector('#freight-value');
  const totalLabel = document.querySelector('#checkout-total');
  const pixPanel = document.querySelector('#pix-panel');
  const cardPanel = document.querySelector('#card-panel');
  const resultPanel = document.querySelector('#payment-result');
  const statusMessage = document.querySelector('#payment-result-message');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let brickController = null;
  let pollTimer = null;
  let pollingReference = null;
  let pollAttempts = 0;
  let lastResultIsDemo = false;
  let demoPixTimer = null;
  const profileUrl = app.dataset.profileUrl || '';
  let successUrl = '';
  const money = (n) => `R$ ${Number(n).toFixed(2).replace('.', ',')}`;
  const deliveryMode = () => form.querySelector('[name="modo_entrega"]:checked')?.value || 'domicilio';
  const shipping = () => deliveryMode() === 'domicilio' ? Number(app.dataset.freight || 0) : 0;
  const total = () => Number(app.dataset.subtotal || 0) + shipping();
  const paymentMode = () => form.querySelector('[name="forma_pagamento"]:checked')?.value || 'PIX';
  const setRequired = (field, required, disabled = false) => {
    if (!field) return;
    field.required = required;
    field.disabled = disabled;
  };
  const isDemo = () => Boolean(window.checkoutConfig?.demoMode);
  const updateDelivery = () => {
    const mode = deliveryMode();
    address.hidden = mode !== 'domicilio';
    pickup.hidden = mode !== 'retirada';
    ['checkout-cep', 'checkout-logradouro', 'checkout-bairro', 'checkout-cidade', 'checkout-estado'].forEach((id) => setRequired(document.getElementById(id), mode === 'domicilio', mode !== 'domicilio'));
    const noNumber = document.querySelector('#sem-numero')?.checked;
    setRequired(form.querySelector('[name="numero"]'), mode === 'domicilio' && !noNumber, mode !== 'domicilio' || noNumber);
    form.querySelectorAll('[name="endereco_salvo"], #sem-numero, #confirmar-logradouro').forEach((f) => { f.disabled = mode !== 'domicilio'; });
    const complement = document.querySelector('#checkout-complemento');
    const noComplement = document.querySelector('#sem-complemento');
    if (noComplement?.checked && mode === 'domicilio') {
      complement.value = '';
      complement.disabled = true;
    }
    else {
      complement.disabled = mode !== 'domicilio';
    }
    setRequired(pickup.querySelector('select'), mode === 'retirada', mode !== 'retirada');
    if (freight) freight.textContent = shipping() ? money(shipping()) : 'Grátis';
    if (totalLabel) totalLabel.textContent = money(total());
    if (paymentMode() === 'Cartão' && !isDemo()) destroyCard().then(mountCard);
  };
  const updateMethod = () => {
    const isCard = paymentMode() === 'Cartão';
    if (pixPanel) pixPanel.hidden = isCard;
    if (cardPanel) cardPanel.hidden = !isCard;
    if (isDemo()) {
      cardPanel?.querySelectorAll('#demo-card-fields input').forEach((field) => {
        field.disabled = !isCard;
        field.required = isCard;
      });
    } else if (isCard) mountCard();
    else destroyCard();
  };
  form.querySelectorAll('[name="modo_entrega"]').forEach((radio) => radio.addEventListener('change', updateDelivery));
  form.querySelectorAll('[name="forma_pagamento"]').forEach((radio) => radio.addEventListener('change', updateMethod));
  document.querySelector('#sem-complemento')?.addEventListener('change', updateDelivery);
  updateDelivery();
  updateMethod();
  const cep = document.querySelector('#checkout-cep');
  const numeroInput = document.querySelector('#checkout-numero');
  const semNumero = document.querySelector('#sem-numero');
  const feedback = document.querySelector('#checkout-cep-feedback');
  const mapBox = document.querySelector('#checkout-map');
  const confirmBox = document.querySelector('#confirmar-logradouro-box');
  const sprite = document.body.dataset.sprite || '/static/icons/sprite.svg';
  const svg = (name) => `<svg class="icon icon-sm" aria-hidden="true"><use href="${sprite}#i-${name}"></use></svg>`;
  const escapeHtml = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let cepRequestId = 0;
  let cepController = null;
  let foraDaArea = '';
  const setFeedback = (text, tone = '', iconName = 'info') => {
    if (!feedback) return;
    feedback.dataset.tone = tone;
    feedback.innerHTML = `${svg(iconName)}<span>${escapeHtml(text)}</span>`;
  };
  const renderMap = (data) => {
    if (!mapBox) return;
    mapBox.hidden = false;
    if (data.mapa) {
      mapBox.innerHTML = `<iframe title="Mapa do endereço de entrega" src="${escapeHtml(data.mapa.embed_url)}" loading="lazy" referrerpolicy="no-referrer"></iframe>
        <p class="map-legend ${data.mapa.preciso ? 'is-exact' : ''}">${svg(data.mapa.preciso ? 'crosshair' : 'map-pin')}${escapeHtml(data.mapa.legenda)}</p>`;
    } else {
      mapBox.innerHTML = `<div class="map-mini-placeholder">${svg('map')}<span>${escapeHtml(data.mapa_mensagem || 'Mapa indisponível neste ambiente.')} O pedido pode ser concluído normalmente.</span></div>`;
    }
  };
  const consultarEndereco = async (preencher = true) => {
    if (!cep) return;
    const digits = cep.value.replace(/\D/g, '');
    if (digits.length !== 8) return;
    const requestId = ++cepRequestId;
    cepController?.abort();
    cepController = new AbortController();
    setFeedback('Consultando CEP e área de entrega…', 'loading', 'clock');
    const params = new URLSearchParams();
    const numero = numeroInput?.value.trim();
    if (semNumero?.checked) params.set('sem_numero', '1');
    else if (numero) params.set('numero', numero);
    const logradouro = document.querySelector('#checkout-logradouro').value.trim();
    if (!preencher && logradouro) params.set('logradouro', logradouro);
    try {
      const url = app.dataset.geoUrl.replace('__CEP__', digits);
      const response = await fetch(`${url}?${params}`, { headers: { Accept: 'application/json' }, signal: cepController.signal });
      const data = await response.json();
      if (requestId !== cepRequestId || digits !== cep.value.replace(/\D/g, '')) return;
      if (!response.ok) {
        const falha = new Error(data.erro || 'CEP indisponível');
        falha.codigo = data.codigo;
        throw falha;
      }
      const a = data.endereco;
      if (preencher) {
        if (a.logradouro) document.querySelector('#checkout-logradouro').value = a.logradouro;
        if (a.bairro) document.querySelector('#checkout-bairro').value = a.bairro;
        document.querySelector('#checkout-cidade').value = a.cidade || '';
        document.querySelector('#checkout-estado').value = a.estado || '';
      }
      cep.removeAttribute('aria-invalid');
      foraDaArea = data.atendido ? '' : (data.area_mensagem || 'Endereço fora da área de entrega.');
      confirmBox.hidden = !data.logradouro_divergente;
      if (data.logradouro_divergente) confirmBox.querySelector('[data-confirm-text]').textContent = `${data.aviso} Marque para confirmar que o logradouro digitado está correto.`;
      if (!data.atendido) {
        setFeedback(foraDaArea, 'error', 'circle-alert');
        cep.setAttribute('aria-invalid', 'true');
      } else if (data.aviso && !data.logradouro_divergente) {
        setFeedback(data.aviso, 'warning', 'triangle-alert');
      } else if (data.numero_erro) {
        setFeedback(data.numero_erro, 'warning', 'triangle-alert');
      } else {
        setFeedback(preencher ? 'Endereço encontrado e dentro da área de entrega. Confira e informe o número.' : 'Endereço dentro da área de entrega.', 'success', 'circle-check');
      }
      renderMap(data);
    } catch (error) {
      if (error.name !== 'AbortError' && requestId === cepRequestId && error.codigo === 'rede') {
        cep.removeAttribute('aria-invalid');
        foraDaArea = '';
        setFeedback(`${error.message} Preencha o endereço manualmente; ele será conferido ao finalizar.`, 'warning', 'wifi-off');
        if (mapBox) mapBox.hidden = true;
      } else if (error.name !== 'AbortError' && requestId === cepRequestId) {
        cep.setAttribute('aria-invalid', 'true');
        setFeedback(error.message || 'Falha ao consultar CEP.', 'error', 'circle-alert');
        if (mapBox) mapBox.hidden = true;
      }
    }
  };
  cep?.addEventListener('blur', () => consultarEndereco(true));
  numeroInput?.addEventListener('change', () => consultarEndereco(false));
  document.querySelector('#checkout-logradouro')?.addEventListener('change', () => consultarEndereco(false));
  semNumero?.addEventListener('change', () => {
    numeroInput.disabled = semNumero.checked;
    numeroInput.required = !semNumero.checked;
    if (semNumero.checked) numeroInput.value = '';
    consultarEndereco(false);
  });

  // Endereços salvos: preenche o formulário automaticamente.
  const preencherSalvo = (radio) => {
    if (!radio?.dataset.endereco) return;
    const e = JSON.parse(radio.dataset.endereco);
    const set = (id, v) => { const f = document.querySelector(id); if (f) f.value = v || ''; };
    set('#checkout-cep', e.cep); set('#checkout-logradouro', e.logradouro); set('#checkout-numero', e.numero);
    set('#checkout-complemento', e.complemento); set('#checkout-bairro', e.bairro); set('#checkout-cidade', e.cidade); set('#checkout-estado', e.uf);
    if (semNumero) { semNumero.checked = e.sem_numero; numeroInput.disabled = e.sem_numero; numeroInput.required = !e.sem_numero; }
    consultarEndereco(false);
  };
  form.querySelectorAll('[name="endereco_salvo"]').forEach((radio) => radio.addEventListener('change', () => {
    if (radio.value) preencherSalvo(radio);
    else {
      ['#checkout-cep', '#checkout-logradouro', '#checkout-numero', '#checkout-complemento', '#checkout-bairro', '#checkout-cidade', '#checkout-estado'].forEach((id) => { document.querySelector(id).value = ''; });
      if (mapBox) mapBox.hidden = true;
      document.querySelector('#checkout-cep').focus();
    }
  }));
  preencherSalvo(form.querySelector('[name="endereco_salvo"]:checked'));

  // Retirada: avisa se a biblioteca escolhida fica longe do CEP informado.
  const pickupCep = document.querySelector('#pickup-cep');
  const pickupFeedback = document.querySelector('#pickup-feedback');
  const pickupSelect = pickup?.querySelector('select');
  const verificarDistancia = async () => {
    const digits = (pickupCep?.value || '').replace(/\D/g, '');
    if (!pickupSelect?.value || digits.length !== 8) { if (pickupFeedback) pickupFeedback.hidden = true; return; }
    pickupFeedback.hidden = false;
    pickupFeedback.dataset.tone = 'loading';
    pickupFeedback.innerHTML = `${svg('clock')}<span>Calculando a distância…</span>`;
    try {
      const response = await fetch(`${app.dataset.distanceUrl}?cep=${digits}&biblioteca_id=${encodeURIComponent(pickupSelect.value)}`, { headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || 'Não foi possível calcular.');
      pickupFeedback.dataset.tone = data.longe ? 'warning' : 'success';
      pickupFeedback.innerHTML = `${svg(data.longe ? 'triangle-alert' : 'navigation')}<span>${escapeHtml(data.mensagem)}</span>`;
    } catch (error) {
      pickupFeedback.dataset.tone = 'error';
      pickupFeedback.innerHTML = `${svg('circle-alert')}<span>${escapeHtml(error.message)}</span>`;
    }
  };
  pickupCep?.addEventListener('blur', verificarDistancia);
  pickupSelect?.addEventListener('change', verificarDistancia);

  const payloadFromForm = () => {
    const data = {};
    new FormData(form).forEach((value, key) => {
      if (key !== '_csrf_token' && !key.startsWith('demo_')) data[key] = value;
    });
    data.termos_aceitos = Boolean(form.querySelector('[name="termos_aceitos"]')?.checked);
    data.consentimento_dados = Boolean(form.querySelector('[name="consentimento_dados"]')?.checked);
    data.sem_complemento = Boolean(form.querySelector('[name="sem_complemento"]')?.checked);
    data.sem_numero = Boolean(semNumero?.checked);
    data.confirmar_logradouro = Boolean(document.querySelector('#confirmar-logradouro')?.checked);
    delete data.endereco_salvo;
    return data;
  };
  const errorBox = document.querySelector('#checkout-error');
  const showFormError = (message) => {
    if (!errorBox) return;
    errorBox.querySelector('span').textContent = message;
    errorBox.hidden = false;
    errorBox.focus();
  };
  const validateDetails = () => {
    if (errorBox) errorBox.hidden = true;
    const fields = [...form.querySelectorAll('input, textarea')].filter((f) => !f.disabled && f.type !== 'hidden' && !f.closest('[hidden]'));
    const invalid = fields.filter((f) => (window.BA?.validarCampo ? !window.BA.validarCampo(f) : !f.checkValidity()));
    if (invalid.length) {
      showFormError('Revise os campos destacados antes de continuar.');
      invalid[0].focus();
      return false;
    }
    if (deliveryMode() === 'domicilio' && foraDaArea) {
      showFormError(foraDaArea);
      cep?.focus();
      return false;
    }
    if (!form.checkValidity()) {
      form.reportValidity();
      return false;
    }
    return true;
  };
  const stopPolling = () => {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    pollingReference = null;
  };
  const startPolling = (reference, mode) => {
    if (pollTimer && pollingReference === reference) return;
    stopPolling();
    pollingReference = reference;
    pollAttempts = 0;
    const url = app.dataset.statusTemplate.replace('__REF__', encodeURIComponent(reference));
    pollTimer = setInterval(async () => {
      pollAttempts += 1;
      try {
        const response = await fetch(url, {
          headers: {
            'Accept': 'application/json'
          }
        });
        const data = await response.json();
        if (response.ok) showResult(data, mode);
      } catch (_) { /* Repetir sem registrar dados privados no console. */
      }
      if (pollAttempts >= 120) stopPolling();
    }, 5000);
  };
  const goToProfileAfterApproval = () => {
    stopPolling();
    const overlay = document.createElement('div');
    overlay.className = 'payment-success-overlay';
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-live', 'polite');
    overlay.innerHTML = '<div class="payment-success-card">' +
      '<svg class="payment-success-icon" viewBox="0 0 96 96" aria-hidden="true">' +
      '<circle class="ring" cx="48" cy="48" r="45" pathLength="189"/>' +
      '<path class="tick" d="M28 50 L42 64 L69 36"/></svg>' +
      '<h2>Pagamento aprovado!</h2>' +
      '<p>Preparando o resumo do seu pedido…</p>' +
      '<div class="payment-success-bar"><span></span></div></div>';
    document.body.appendChild(overlay);
    setTimeout(() => window.location.replace(successUrl || profileUrl), 2200);
  };
  const confirmDemoPix = async (reference, attempt = 0) => {
    demoPixTimer = null;
    try {
      const url = app.dataset.statusTemplate.replace('__REF__', encodeURIComponent(reference));
      const response = await fetch(url, {
        headers: {
          'Accept': 'application/json'
        }
      });
      const data = await response.json();
      if (response.ok && data.status === 'approved') {
        if (data.sucesso_url) successUrl = data.sucesso_url;
        goToProfileAfterApproval();
        return;
      }
    } catch (_) { /* Repetir abaixo. */
    }
    if (attempt < 10) demoPixTimer = setTimeout(() => confirmDemoPix(reference, attempt + 1), 1000);
  };
  const showResult = (data, mode) => {
    if (data?.sucesso_url) successUrl = data.sucesso_url;
    if (!resultPanel) return;
    if (demoPixTimer) clearTimeout(demoPixTimer);
    demoPixTimer = null;
    if (data.status === 'approved' && profileUrl) {
      stopPolling();
      goToProfileAfterApproval();
      return;
    }
    resultPanel.hidden = false;
    lastResultIsDemo = Boolean(data.demo);
    const title = document.querySelector('#payment-result-title');
    const qr = document.querySelector('#payment-qr');
    const copyLabel = document.querySelector('#pix-copy-label');
    const copyButton = document.querySelector('#copy-pix');
    const ticket = document.querySelector('#payment-ticket');
    const failed = ['rejected', 'cancelled', 'canceled'].includes(data.status);
    if (data.demo) {
      title.textContent = 'QRCode gerado';
    } else {
      title.textContent = failed ? 'Pagamento não aprovado' : 'Pagamento aguardando confirmação';
      statusMessage.textContent = failed ? 'O pagamento foi recusado ou cancelado. Verifique os dados ou tente novamente.' : 'Pedido registrado. A confirmação será atualizada automaticamente quando o provedor informar o status.';
    }
    if (data.qr_code_base64 && mode === 'PIX') {
      qr.src = `data:image/png;base64,${data.qr_code_base64}`;
      qr.hidden = false;
    }
    else {
      qr.hidden = true;
      qr.removeAttribute('src');
    }
    if (data.qr_code && mode === 'PIX') {
      document.querySelector('#pix-copy').value = data.qr_code;
      copyLabel.hidden = false;
      copyButton.hidden = false;
    }
    else {
      copyLabel.hidden = true;
      copyButton.hidden = true;
    }
    if (data.ticket_url && !data.demo) {
      ticket.href = data.ticket_url;
      ticket.hidden = false;
    }
    else {
      ticket.hidden = true;
    }
    if (data.demo && mode === 'PIX' && data.order_reference) {
      const delay = Number(data.auto_accept_seconds || 5) * 1000;
      const reference = data.order_reference;
      demoPixTimer = setTimeout(() => confirmDemoPix(reference), delay);
      stopPolling();
    } else if (data.order_reference && !failed && !data.demo) startPolling(data.order_reference, mode);
    else stopPolling();
    resultPanel.scrollIntoView({
      behavior: 'smooth', block: 'center'
    });
  };
  // Cartão: sucesso vai direto ao perfil, sem painel intermediário.
  const handleCardResult = (data) => {
    if (data?.sucesso_url) successUrl = data.sucesso_url;
    if (data.status === 'approved' && profileUrl) {
      goToProfileAfterApproval();
      return;
    }
    if (['pending', 'in_process'].includes(data.status)) {
      showResult(data, 'Cartão');
      return;
    }
    throw new Error('O pagamento não foi aprovado. Confira os dados do cartão ou tente outro meio de pagamento.');
  };
  document.querySelector('#copy-pix')?.addEventListener('click', async () => {
    const field = document.querySelector('#pix-copy');
    try {
      await navigator.clipboard.writeText(field.value);
      statusMessage.textContent = lastResultIsDemo ? 'Código fictício copiado. Ele não pode ser usado para pagar.' : 'Código Pix copiado. Abra o aplicativo do seu banco para pagar.';
    } catch (_) {
      field.select();
      document.execCommand('copy');
    }
  });
  const postJson = async (url, body) => {
    const response = await fetch(url, {
      method: 'POST', headers: {
        'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Accept': 'application/json'
      }, body: JSON.stringify(body)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      const error = new Error(data.error || 'Não foi possível iniciar o pagamento.');
      error.campo = data.campo;
      error.codigo = data.codigo;
      throw error;
    }
    return data;
  };
  const showError = (title, error) => {
    if (error?.campo) {
      const field = form.querySelector(`[name="${error.campo}"]`);
      if (error.codigo === 'logradouro_divergente' && confirmBox) {
        confirmBox.hidden = false;
        confirmBox.querySelector('[data-confirm-text]').textContent = `${error.message} Marque esta opção e envie de novo.`;
      }
      if (field && window.BA?.validarCampo) {
        field.setAttribute('aria-invalid', 'true');
      }
      showFormError(error.message);
      field?.focus();
      return;
    }
    resultPanel.hidden = false;
    document.querySelector('#payment-result-title').textContent = title;
    statusMessage.textContent = error.message || 'Não foi possível continuar.';
  };
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!validateDetails()) return;
    if (paymentMode() === 'PIX') {
      const button = document.querySelector('#pix-submit');
      if (!button) return;
      button.disabled = true;
      button.textContent = isDemo() ? 'Gerando QRCode...' : 'Gerando Pix…';
      try {
        showResult(await postJson(app.dataset.pixUrl, payloadFromForm()), 'PIX');
      } catch (error) {
        showError(isDemo() ? 'Falha' : 'Não foi possível gerar o Pix', error);
      }
      finally {
        button.disabled = false;
        button.textContent = isDemo() ? 'Gerar QRCODE' : 'Gerar Pix e confirmar pedido';
      }
      return;
    }
    if (isDemo()) {
      const button = document.querySelector('#demo-card-submit');
      if (!button) return;
      button.disabled = true;
      button.textContent = 'Processando…';
      try {
        handleCardResult(await postJson(app.dataset.cardUrl, {
          ...payloadFromForm(), demo_card_confirmed: true
        }));
      }
      catch (error) {
        showError('Não foi possível concluir o pagamento', error);
        cardPanel?.querySelectorAll('#demo-card-fields input').forEach((field) => {
          field.value = '';
        });
        button.disabled = false;
        button.textContent = 'Finalizar pagamento';
      }
    }
    // No modo real o próprio Mercado Pago Card Payment Brick envia o token.
  });
  async function destroyCard() {
    const current = brickController;
    brickController = null;
    if (current?.unmount) {
      try {
        await current.unmount();
      } catch (_) { /* noop */
      }
    }
  }
  async function mountCard() {
    if (isDemo() || !window.checkoutConfig?.paymentsEnabled || !window.checkoutConfig.publicKey || !window.MercadoPago || brickController) return;
    try {
      const mp = new window.MercadoPago(window.checkoutConfig.publicKey, {
        locale: 'pt-BR'
      });
      const bricks = mp.bricks();
      brickController = await bricks.create('cardPayment', 'cardPaymentBrick_container', {
        initialization: {
          amount: total(), payer: {
            email: form.elements.email.value, identification: {
              type: 'CPF', number: form.elements.cpf.value.replace(/\D/g, '')
            }
          }
        },
        callbacks: {
          onReady: () => {},
          onSubmit: async (cardData) => {
            if (!validateDetails()) throw new Error('Confira os campos obrigatórios do pedido.');
            try {
              handleCardResult(await postJson(app.dataset.cardUrl, {
                ...payloadFromForm(), card: cardData
              }));
            }
            catch (error) {
              showError('Não foi possível concluir o pagamento', error);
              throw error;
            }
          },
          onError: () => {
            statusMessage.textContent = 'O formulário seguro do cartão encontrou um erro. Revise os dados e tente novamente.';
          }
        }
      });
    } catch (_) {
      statusMessage.textContent = 'Não foi possível carregar o formulário seguro. Atualize a página e tente novamente.';
    }
  }
});

