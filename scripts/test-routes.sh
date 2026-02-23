#!/bin/bash
#
# Test all processor routes
# Run with: ./scripts/test-routes.sh
#

set -e

BASE_URL="${BASE_URL:-http://localhost:8090}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

test_endpoint() {
    local method="$1"
    local endpoint="$2"
    local expected_status="$3"
    local data="$4"
    local description="$5"

    local url="${BASE_URL}${endpoint}"
    local response
    local status

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$url")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST -H "Content-Type: application/json" -d "$data" "$url")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE -H "Content-Type: application/json" -d "$data" "$url")
    fi

    status=$(echo "$response" | tail -1)
    body=$(echo "$response" | sed '$d')

    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} $method $endpoint ($description)"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗${NC} $method $endpoint - expected $expected_status, got $status"
        echo "  Response: $(echo "$body" | head -c 200)"
        FAILED=$((FAILED + 1))
    fi
}

test_json_field() {
    local endpoint="$1"
    local field="$2"
    local description="$3"

    local response=$(curl -s "${BASE_URL}${endpoint}")
    local value=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print($field)" 2>/dev/null)

    if [ -n "$value" ] && [ "$value" != "None" ]; then
        echo -e "${GREEN}✓${NC} $endpoint has $description: $value"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗${NC} $endpoint missing $description"
        FAILED=$((FAILED + 1))
    fi
}

echo ""
echo -e "${YELLOW}Testing Processor Routes${NC}"
echo "========================="
echo ""

# Health endpoint
echo -e "${YELLOW}Health Check${NC}"
test_endpoint "GET" "/health" "200" "" "health check"
test_json_field "/health" "d['status']" "status field"

# Dashboard routes
echo ""
echo -e "${YELLOW}Dashboard Routes${NC}"
test_endpoint "GET" "/" "200" "" "main dashboard"
test_endpoint "GET" "/dashboard" "200" "" "dashboard alias"
test_endpoint "GET" "/api/dashboard" "200" "" "dashboard API"
test_json_field "/api/dashboard" "d['stats']['total']" "total notifications"
test_json_field "/api/dashboard" "d['connection']['status']" "connection status"

# Status routes
echo ""
echo -e "${YELLOW}Status Routes${NC}"
test_endpoint "GET" "/status" "200" "" "status page"
test_endpoint "GET" "/api/status" "200" "" "status API"
test_json_field "/api/status" "len(d['core'])" "core services count"
test_json_field "/api/status" "len(d['sinks'])" "sinks count"

# Rules routes
echo ""
echo -e "${YELLOW}Rules Routes${NC}"
test_endpoint "GET" "/rules" "200" "" "rules page"
test_endpoint "GET" "/api/rules" "200" "" "rules API"
test_json_field "/api/rules" "len(d['rules'])" "rules count"
test_json_field "/api/rules" "len(d['matchers'])" "matchers count"

# Insights routes
echo ""
echo -e "${YELLOW}Insights Routes${NC}"
test_endpoint "GET" "/api/insights" "200" "" "insights API"
test_endpoint "GET" "/api/insights/ai" "200" "" "AI insights API"

# Notification endpoint (test with minimal payload)
echo ""
echo -e "${YELLOW}Notification Route${NC}"
NOTIF_DATA='{"app":"test","title":"Route Test","body":"Testing routes"}'
test_endpoint "POST" "/notification" "200" "$NOTIF_DATA" "notification processing"

# Summary
echo ""
echo "========================="
echo -e "Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo ""

if [ $FAILED -gt 0 ]; then
    exit 1
fi
