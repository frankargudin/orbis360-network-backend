#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Orbis360 — Simulador de fallos de red
#
# Uso:
#   ./simulate_failure.sh core-switch    # Tumba el core switch (cascada)
#   ./simulate_failure.sh ap             # Tumba un AP (fallo aislado)
#   ./simulate_failure.sh floor3         # Tumba todo el piso 3
#   ./simulate_failure.sh restore        # Restaura todos los dispositivos
#   ./simulate_failure.sh random         # Tumba un dispositivo al azar
# ═══════════════════════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

case "${1:-help}" in
  core-switch)
    echo -e "${RED}═══ SIMULACIÓN: Caída del Core Switch ═══${NC}"
    echo -e "${YELLOW}Esto causará una caída en cascada de TODOS los dispositivos${NC}"
    echo -e "${YELLOW}downstream (switches de distribución, APs, servidor)${NC}"
    echo ""
    docker stop sim-core-switch-01
    echo -e "${RED}✗ sim-core-switch-01 DETENIDO${NC}"
    echo ""
    echo "El monitor detectará la caída en ~45 segundos (3 checks × 15s)"
    echo "El RCA debería identificar el core-switch como causa raíz"
    echo ""
    echo -e "Para restaurar: ${GREEN}./simulate_failure.sh restore${NC}"
    ;;

  core-router)
    echo -e "${RED}═══ SIMULACIÓN: Caída del Core Router ═══${NC}"
    docker stop sim-core-router-01
    echo -e "${RED}✗ sim-core-router-01 DETENIDO${NC}"
    echo "Caída total de la red interna"
    ;;

  ap)
    echo -e "${RED}═══ SIMULACIÓN: Caída de un Access Point ═══${NC}"
    docker stop sim-ap-f2-01
    echo -e "${RED}✗ sim-ap-f2-01 DETENIDO${NC}"
    echo "Fallo aislado — solo este AP debería aparecer como DOWN"
    echo "El RCA NO debería activarse (es un solo dispositivo)"
    ;;

  floor3)
    echo -e "${RED}═══ SIMULACIÓN: Caída de todo el Piso 3 ═══${NC}"
    docker stop sim-dist-switch-f3 sim-ap-f3-01 sim-server-dc-01
    echo -e "${RED}✗ sim-dist-switch-f3 DETENIDO${NC}"
    echo -e "${RED}✗ sim-ap-f3-01 DETENIDO${NC}"
    echo -e "${RED}✗ sim-server-dc-01 DETENIDO${NC}"
    echo "El RCA debería identificar dist-switch-f3 como causa raíz del piso 3"
    ;;

  server)
    echo -e "${RED}═══ SIMULACIÓN: Caída del servidor DC ═══${NC}"
    docker stop sim-server-dc-01
    echo -e "${RED}✗ sim-server-dc-01 DETENIDO${NC}"
    echo "Fallo crítico aislado — servidor"
    ;;

  firewall)
    echo -e "${RED}═══ SIMULACIÓN: Caída del Firewall ═══${NC}"
    docker stop sim-firewall-01
    echo -e "${RED}✗ sim-firewall-01 DETENIDO${NC}"
    echo "Gateway caído — sin acceso a Internet"
    ;;

  random)
    DEVICES=("sim-core-router-01" "sim-core-switch-01" "sim-dist-switch-f2" "sim-dist-switch-f3" "sim-ap-f2-01" "sim-ap-f3-01" "sim-server-dc-01" "sim-firewall-01")
    RANDOM_DEVICE=${DEVICES[$RANDOM % ${#DEVICES[@]}]}
    echo -e "${RED}═══ SIMULACIÓN: Fallo aleatorio ═══${NC}"
    docker stop "$RANDOM_DEVICE"
    echo -e "${RED}✗ $RANDOM_DEVICE DETENIDO${NC}"
    ;;

  restore)
    echo -e "${GREEN}═══ RESTAURANDO todos los dispositivos ═══${NC}"
    docker start sim-firewall-01 sim-core-router-01 sim-core-switch-01 \
      sim-dist-switch-f2 sim-dist-switch-f3 \
      sim-ap-f2-01 sim-ap-f3-01 sim-server-dc-01 2>/dev/null
    echo -e "${GREEN}✓ Todos los dispositivos restaurados${NC}"
    echo "El monitor detectará la recuperación en ~15 segundos"
    ;;

  status)
    echo "═══ Estado de dispositivos simulados ═══"
    for c in sim-firewall-01 sim-core-router-01 sim-core-switch-01 sim-dist-switch-f2 sim-dist-switch-f3 sim-ap-f2-01 sim-ap-f3-01 sim-server-dc-01; do
      STATUS=$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || echo "not found")
      if [ "$STATUS" = "true" ]; then
        IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$c")
        echo -e "  ${GREEN}● UP${NC}   $c ($IP)"
      else
        echo -e "  ${RED}● DOWN${NC} $c"
      fi
    done
    ;;

  *)
    echo "Orbis360 — Simulador de fallos de red"
    echo ""
    echo "Uso: $0 <escenario>"
    echo ""
    echo "Escenarios disponibles:"
    echo "  core-switch   Tumba el core switch (caída en cascada)"
    echo "  core-router   Tumba el core router (caída total)"
    echo "  ap            Tumba un AP (fallo aislado)"
    echo "  floor3        Tumba todo el piso 3"
    echo "  server        Tumba el servidor DC"
    echo "  firewall      Tumba el firewall"
    echo "  random        Tumba un dispositivo al azar"
    echo "  restore       Restaura todos los dispositivos"
    echo "  status        Muestra el estado actual"
    ;;
esac
