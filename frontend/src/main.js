import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 【【【 在这里引入深色主题的核心CSS变量文件 】】】
import 'element-plus/theme-chalk/dark/css-vars.css'


const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(ElementPlus)
app.mount('#app')