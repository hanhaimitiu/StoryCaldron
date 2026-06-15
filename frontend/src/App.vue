<template>
  <div class="app-container">
    <header class="header">
      <h1>📖 StoryCaldron</h1>
      <p>小说创作助手</p>
      <div class="nav-tabs">
        <router-link 
          to="/parse" 
          class="nav-tab"
          active-class="active"
        >
          📊 小说解析
        </router-link>
        <router-link 
          to="/write" 
          class="nav-tab"
          active-class="active"
        >
          ✍️ 小说创作
        </router-link>
      </div>
    </header>

    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </div>
</template>

<script setup>
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  min-height: 100vh;
  font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  text-align: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 2px solid #443828;
}

.header h1 {
  font-size: 28px;
  color: #d4b886;
  letter-spacing: 4px;
  margin-bottom: 8px;
}

.header p {
  color: #8c724a;
  font-size: 14px;
  margin: 0 0 15px 0;
}

.nav-tabs {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 10px;
}

.nav-tab {
  background: rgba(140, 114, 74, 0.2);
  border: 1px solid #443828;
  border-radius: 8px;
  padding: 8px 20px;
  color: #8c724a;
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.3s;
}

.nav-tab:hover {
  background: rgba(140, 114, 74, 0.3);
  color: #d4b886;
}

.nav-tab.active {
  background: linear-gradient(145deg, #8c6d4e, #6b5a40);
  border-color: #d4b886;
  color: #d4b886;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
