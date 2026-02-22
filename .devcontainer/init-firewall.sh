#!/usr/bin/env bash
set -euo pipefail

echo "Configuring firewall..."

# Idempotency: destroy existing ipset if present
if ipset list allowed-domains &>/dev/null; then
    iptables -D OUTPUT -m set --match-set allowed-domains dst -j ACCEPT 2>/dev/null || true
    ipset destroy allowed-domains
fi

# Create ipset for allowed destination IPs
ipset create allowed-domains hash:net

# --- GitHub IP ranges ---
echo "Fetching GitHub IP ranges..."
GITHUB_META=$(curl -s --max-time 10 https://api.github.com/meta)
for cidr in $(echo "${GITHUB_META}" | jq -r '.web[], .api[], .git[]' 2>/dev/null | sort -u); do
    ipset add allowed-domains "${cidr}" 2>/dev/null || true
done

# --- Allowed domains (resolved to IPs) ---
ALLOWED_DOMAINS=(
    "api.anthropic.com"
    "pypi.org"
    "files.pythonhosted.org"
    "graph.microsoft.com"
    "login.microsoftonline.com"
    "management.azure.com"
    "func-semfolder-dev.azurewebsites.net"
    "func-semfolder-dev.scm.azurewebsites.net"
    "stsemfolderdev.blob.core.windows.net"
    "registry.terraform.io"
    "releases.hashicorp.com"
    "checkpoint-api.hashicorp.com"
    "packages.microsoft.com"
    "deb.nodesource.com"
    "registry.npmjs.org"
)

echo "Resolving allowed domains..."
for domain in "${ALLOWED_DOMAINS[@]}"; do
    ips=$(dig +short "${domain}" A 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)
    for ip in ${ips}; do
        ipset add allowed-domains "${ip}/32" 2>/dev/null || true
    done
done

# --- Apply iptables rules ---
# Flush existing OUTPUT rules (preserve DOCKER rules if present)
iptables -F OUTPUT 2>/dev/null || true

# Allow loopback
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established/related connections
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow DNS (UDP + TCP port 53)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow traffic to whitelisted IPs
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Default deny all other outbound traffic
iptables -P OUTPUT DROP

echo "Firewall configured successfully."
echo "Allowed: Anthropic API, PyPI, GitHub, Azure (Graph, login, storage, functions), Terraform, npm"
echo "Blocked: all other outbound traffic"
