(() => {
  class LiveResultsPoller {
    constructor(options) {
      this.date = options.date; this.refresh = options.refresh || (async () => {});
      this.remaining = 300; this.deadline = Date.now() + 300000; this.inFlight = false; this.completed = false;
      this.root = document.getElementById(options.rootId || 'live-results-panel');
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) this.deadline = Math.max(this.deadline, Date.now() + 900000);
        else { this.remaining = 0; this.tick(); }
      });
      this.timer = window.setInterval(() => this.tick(), 1000); this.check();
    }
    tick() { this.remaining = Math.max(0, Math.ceil((this.deadline-Date.now())/1000)); this.renderCountdown(); if (this.remaining <= 0 && !this.inFlight) this.check(); }
    renderCountdown() {
      const node = this.root?.querySelector('[data-live-countdown]'); if (!node) return;
      node.textContent = `${String(Math.floor(this.remaining / 60)).padStart(2,'0')}:${String(this.remaining % 60).padStart(2,'0')}`;
    }
    render(data, failed=false) {
      if (!this.root) return;
      const status=this.root.querySelector('[data-live-status]'), checked=this.root.querySelector('[data-live-checked]'), tracks=this.root.querySelector('[data-live-tracks]');
      status.textContent=failed?'Son istek başarısız':(data.status||'UNKNOWN'); status.className=`status-pill ${failed||data.status==='FAILED'?'danger':data.status==='SUCCESS'?'ok':'warn'}`;
      checked.textContent=data.ended_at?new Date(data.ended_at).toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'}):'Henüz yok';
      const next=this.root.querySelector('[data-live-next]'),server=this.root.querySelector('[data-live-server]');
      if(next)next.textContent=data.next_run_at?new Date(data.next_run_at).toLocaleTimeString('tr-TR'):'—';
      if(server)server.textContent=data.server_now?new Date(data.server_now).toLocaleTimeString('tr-TR'):'—';
      tracks.innerHTML=(data.tracks||[]).map(t=>`<span class="live-track ${t.completed?'complete':''}">${this.escape(t.track)} <b>${t.result_races}/${t.program_races}</b>${t.completed?' ✓':''}</span>`).join('');
    }
    escape(value) { const node=document.createElement('span'); node.textContent=value??''; return node.innerHTML; }
    async check() {
      if (this.inFlight) return; this.inFlight=true;
      try {
        const date=typeof this.date==='function'?this.date():this.date, query=new URLSearchParams({country:'ALL'}); if(date)query.set('date',date);
        const response=await fetch(`/api/results-refresh/status?${query}`); if(!response.ok)throw new Error(await response.text()); const data=await response.json();
        this.completed=data.total_tracks>0&&data.completed_tracks===data.total_tracks; this.remaining=Number(data.seconds_remaining??data.interval_seconds??300); this.deadline=Date.now()+Math.max(15,this.remaining)*1000; this.render(data); await this.refresh();
      } catch(error) { this.completed=false; this.remaining=300; this.deadline=Date.now()+300000; this.render({status:'FAILED',tracks:[]},true); console.warn('live results refresh failed',error); }
      finally { this.inFlight=false; this.renderCountdown(); }
    }
  }
  window.LiveResultsPoller=LiveResultsPoller;
})();
