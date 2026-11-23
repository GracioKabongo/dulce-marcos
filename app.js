(() => {
  const revealNodes = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('is-visible'); observer.unobserve(entry.target); } });
    }, { threshold: 0.08, rootMargin:'0px 0px -30px 0px' });
    revealNodes.forEach(node => observer.observe(node));
  } else revealNodes.forEach(node => node.classList.add('is-visible'));


  const envelopeTrigger = document.getElementById('envelope-trigger');
  if (envelopeTrigger) {
    envelopeTrigger.addEventListener('click', () => {
      const open = envelopeTrigger.classList.toggle('is-open');
      envelopeTrigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  const eventDate = new Date('2026-12-04T18:00:00+02:00');
  const daysEl = document.getElementById('countdown-days');
  const hoursEl = document.getElementById('countdown-hours');
  const minutesEl = document.getElementById('countdown-minutes');
  const secondsEl = document.getElementById('countdown-seconds');
  const pad = value => String(value).padStart(2, '0');
  const renderCountdown = () => {
    if (!daysEl || !hoursEl || !minutesEl || !secondsEl) return;
    const diff = eventDate.getTime() - Date.now();
    if (diff <= 0) {
      daysEl.textContent = '00';
      hoursEl.textContent = '00';
      minutesEl.textContent = '00';
      secondsEl.textContent = '00';
      return;
    }
    const totalSeconds = Math.floor(diff / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    daysEl.textContent = pad(days);
    hoursEl.textContent = pad(hours);
    minutesEl.textContent = pad(minutes);
    secondsEl.textContent = pad(seconds);
  };
  renderCountdown();
  setInterval(renderCountdown, 1000);

  const form = document.getElementById('rsvp-form');
  const nameInput = document.getElementById('guest-name');
  const feedback = document.getElementById('form-feedback');
  const submit = document.getElementById('submit-rsvp');
  const success = document.getElementById('rsvp-success');
  const formView = document.getElementById('rsvp-form-view');
  const edit = document.getElementById('edit-rsvp');
  const storageKey = 'dulce_50_guest_token_v1';
  let token = '';
  const makeToken = () => {
    if (crypto.randomUUID) return crypto.randomUUID().replaceAll('-', '');
    const bytes = new Uint8Array(24); crypto.getRandomValues(bytes);
    return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  };
  try { token = localStorage.getItem(storageKey) || makeToken(); localStorage.setItem(storageKey, token); }
  catch { token = makeToken(); }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    feedback.textContent = '';
    const name = nameInput.value.trim().replace(/\s+/g,' ');
    const selected = form.querySelector('input[name="attending"]:checked');
    if (name.length < 3) { feedback.textContent = 'Indique o seu nome completo para continuar.'; nameInput.focus(); return; }
    if (!selected) { feedback.textContent = 'Seleccione uma das opções de presença.'; return; }
    if (!token) { feedback.textContent = 'Não foi possível preparar a confirmação. Actualize a página.'; return; }
    const original = submit.innerHTML;
    submit.disabled = true;
    submit.innerHTML = 'A registar a sua resposta…';
    try {
      const res = await fetch('/api/rsvp', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name,attending:selected.value,guest_token:token,contact_site:form.elements.contact_site.value}) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.saved) throw new Error(data.detail || data.message || 'Não foi possível registar a resposta. Tente novamente.');
      document.getElementById('success-heading').textContent = selected.value === 'sim' ? 'Até breve!' : 'Obrigada pela resposta!';
      document.getElementById('success-message').textContent = selected.value === 'sim'
        ? `Obrigado, ${name}. A sua presença foi confirmada. Será uma alegria recebê-lo(a) nesta celebração.`
        : `Obrigado, ${name}. A sua resposta foi registada. Sentiremos a sua falta neste momento especial.`;
      formView.hidden = true;
      success.hidden = false;
      success.focus?.();
    } catch (e) { feedback.textContent = e.message === 'Failed to fetch' ? 'Não foi possível comunicar com o servidor. Verifique a ligação e tente novamente.' : e.message; }
    finally { submit.disabled = false; submit.innerHTML = original; }
  });
  edit.addEventListener('click', () => { success.hidden = true; formView.hidden = false; feedback.textContent = ''; nameInput.focus(); });
})();
