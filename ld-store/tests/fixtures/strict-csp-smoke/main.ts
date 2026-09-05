import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import StrictCspSmoke from './StrictCspSmoke.vue'
import '@/styles/tokens.css'
import '@/styles/main.css'
import '@/styles/seller.css'
import './smoke.css'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:pathMatch(.*)*', component: StrictCspSmoke }]
})

createApp(StrictCspSmoke)
  .use(createPinia())
  .use(router)
  .mount('#app')
