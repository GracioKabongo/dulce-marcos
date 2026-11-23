(() => {
  const byId = id => document.getElementById(id);
  let cache = [];
  const showLogin = () => { byId('dashboard').hidden = true; byId('login-view').hidden = false; byId('logout').hidden = true; };
  const showDash = () => { byId('dashboard').hidden = false; byId('login-view').hidden = true; byId('logout').hidden = false; };
  const esc = v => String(v ?? '').replace(/[&<>"']/g, s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const when = v => {try{return new Date(v).toLocaleString('pt-PT',{timeZone:'Africa/Maputo',dateStyle:'short',timeStyle:'short'});}catch{return v;}};
  async function refresh(){
    byId('admin-error').textContent='';
    const response = await fetch('/api/admin/rsvps');
    if (response.status === 401 || response.status === 503) { showLogin(); return; }
    if (!response.ok) { byId('admin-error').textContent='Não foi possível carregar os dados.'; return; }
    const data = await response.json(); cache = data.items; showDash();
    byId('count-total').textContent=data.counts.total;
    byId('count-sim').textContent=data.counts.sim;
    byId('count-nao').textContent=data.counts.nao;
    byId('count-pending').textContent=data.counts.pending+data.counts.failed;
    byId('wa-notice').hidden=data.whatsapp_configured;
    render();
  }
  function render(){
    const q=byId('search').value.trim().toLowerCase();
    const rows=cache.filter(r=>r.guest_name.toLowerCase().includes(q));
    byId('rows').innerHTML = rows.map(r=>{
      let c=r.notification_state==='aceite_pela_api'?'ok':r.notification_state==='falhou'?'fail':'pending';
      let state=r.notification_state==='aceite_pela_api'?'Aceite pela API':r.notification_state==='falhou'?'Falhou':'Pendente';
      return `<tr><td><strong>${esc(r.guest_name)}</strong></td><td>${r.attending==='sim'?'Presente':'Não comparece'}</td><td>${esc(when(r.updated_at))}</td><td><span class="status ${c}" title="${esc(r.notification_error)}">${state}</span></td><td><button class="tertiary" type="button" data-remove="${esc(r.id)}">Eliminar</button></td></tr>`;
    }).join('') || '<tr><td colspan="5">Sem respostas.</td></tr>';
    byId('status').textContent=`${rows.length} resultado(s)`;
  }
  byId('login-form').addEventListener('submit', async e=>{
    e.preventDefault();byId('login-error').textContent='';
    try{ const res=await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:byId('password').value})});const data=await res.json();if(!res.ok)throw Error(data.detail||'Acesso negado');byId('password').value='';await refresh();}catch(err){byId('login-error').textContent=err.message;}
  });
  byId('logout').addEventListener('click', async()=>{await fetch('/api/admin/logout',{method:'POST'});showLogin();});
  byId('refresh').addEventListener('click',refresh);
  byId('search').addEventListener('input',render);
  byId('export').addEventListener('click',()=>location.href='/api/admin/export');
  byId('retry').addEventListener('click',async()=>{
    const res=await fetch('/api/admin/retry',{method:'POST'});
    if(res.ok){const d=await res.json();if(!d.configured)byId('admin-error').textContent='Configure a integração com WhatsApp antes de reenviar.';else byId('admin-error').textContent=`Aceites pela API: ${d.accepted_by_api} de ${d.processed}.`;await refresh();}else byId('admin-error').textContent='Não foi possível reenviar.';
  });
  byId('rows').addEventListener('click',async e=>{
    const b=e.target.closest('[data-remove]');if(!b)return;
    if(!confirm('Eliminar esta confirmação? Esta acção não pode ser revertida.'))return;
    const r=await fetch('/api/admin/rsvps/'+encodeURIComponent(b.dataset.remove),{method:'DELETE'});
    if(r.ok)await refresh();else byId('admin-error').textContent='Não foi possível eliminar a confirmação.';
  });
  refresh().catch(()=>showLogin());
})();
