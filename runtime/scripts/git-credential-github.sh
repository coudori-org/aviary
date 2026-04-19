#!/bin/bash
# Git credential helper for GitHub — reads GITHUB_TOKEN from environment.
# Configured via GIT_CONFIG_* env vars in agent.ts.
if [ "$1" = "get" ]; then
    if [ -n "$GITHUB_TOKEN" ]; then
        echo "protocol=https"
        echo "host=github.com"
        echo "username=x-access-token"
        echo "password=$GITHUB_TOKEN"
    fi
fi
