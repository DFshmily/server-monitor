<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useServersStore } from '../stores/servers'
import { storeToRefs } from 'pinia'
import ServerMap from '../components/ServerMap.vue'

const store = useServersStore()
const { serverList } = storeToRefs(store)

onMounted(async () => {
  await store.fetchServers()
  for (const server of serverList.value) {
    store.fetchLatest(server.name)
  }
  store.connectWebSocket()
})

onUnmounted(() => {
  store.disconnectWebSocket()
})
</script>

<template>
  <ServerMap :servers="serverList" />
</template>
