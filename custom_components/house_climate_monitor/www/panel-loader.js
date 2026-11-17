/* Stable sidebar panel loader; version is the manifest's published release. */
class HouseClimateMonitorLoader extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._hass=null;this._active=null;this._timer=null;this._version=null;this._working=false;
    this.shadowRoot.innerHTML='<style>:host{display:block;color:var(--primary-text-color)}#status{padding:12px;color:var(--secondary-text-color)}</style><div id="status"></div><div id="mount"></div>';
  }
  set hass(v){this._hass=v;if(this._active)this._active.hass=v;}
  set panel(v){this._panel=v;if(this._active)this._active.panel=v;}
  set route(v){this._route=v;if(this._active)this._active.route=v;}
  set narrow(v){this._narrow=v;if(this._active)this._active.narrow=v;}
  connectedCallback(){this._check();this._timer=window.setInterval(()=>this._check(),60000);}
  disconnectedCallback(){if(this._timer)clearInterval(this._timer);}
  async _check(){if(this._working||!this.isConnected)return;this._working=true;
    try {const v=this._panel?.config?.integration_version||this._version||'0.1.0';
      const tag='house-climate-monitor-panel-v'+v.replace(/\./g,'-');
      if(!customElements.get(tag))await import('/house_climate_monitor/assets/'+v+'/managed-panel.js?v='+v);
      const el=document.createElement(tag);el.hass=this._hass;el.panel=this._panel;el.route=this._route;el.narrow=this._narrow;
      if(v!==this._version){this.shadowRoot.querySelector('#mount').replaceChildren(el);this._active=el;this._version=v;}
      this.shadowRoot.querySelector('#status').textContent='';
    }catch(e){this.shadowRoot.querySelector('#status').textContent='Climate Monitor panel could not load: '+e.message;}
    finally{this._working=false;}
  }
}
if(!customElements.get('house-climate-monitor-loader'))customElements.define('house-climate-monitor-loader',HouseClimateMonitorLoader);
