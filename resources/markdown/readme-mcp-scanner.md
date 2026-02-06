# MCP Scanner Security Tool

## 🎯 Quick Start - Your Scan Results

**Status**: ✅ Initial scan completed successfully on 2026-02-06

### Summary
- **Servers Scanned**: 5 out of 6
- **Tools Analyzed**: 33
- **Safe Tools**: 31 (94%)
- **Security Findings**: 2 HIGH-severity (Context7 server)
- **Overall Risk**: 🟢 LOW

📊 **[View Detailed Results](../../scripts/python/mcp_scan_summary.md)**

### What Was Found
- ✅ **fetch, filesystem, sequentialthinking, jupyter-mcp-server**: All tools safe
- ⚠️ **context7**: 2 tools flagged for "coercive injection" (imperative language in descriptions)
- ❌ **transcript-api**: Authentication failed (token needs updating)

**Action Required**: Update transcript-api bearer token. See [recommendations](#security-recommendations) below.

---

## Overview

The **MCP Scanner** is a comprehensive security analysis tool developed by Cisco AI Defense for scanning Model Context Protocol (MCP) servers and tools for potential security vulnerabilities. It combines multiple detection engines to identify threats in MCP configurations, tools, prompts, resources, and server instructions.

Repository: [cisco-ai-defense/mcp-scanner](https://github.com/cisco-ai-defense/mcp-scanner)

## Key Features

### Multi-Engine Security Analysis

The MCP Scanner provides three powerful scanning engines that can be used independently or together:

#### 1. **YARA Analyzer** (No API Key Required)
- Pattern-based threat detection using YARA rules
- Detects suspicious code patterns, command injection risks, file access violations
- Fast, offline scanning capability
- Ideal for CI/CD pipelines and air-gapped environments
- **Recommended for initial scans**

#### 2. **LLM Analyzer** (Requires LLM API Key)
- Semantic analysis using large language models
- LLM-as-a-judge approach for detecting:
  - Prompt injection attacks
  - Tool poisoning
  - Misleading documentation
  - Behavioral anomalies
- Supports multiple LLM providers:
  - OpenAI GPT-4o/4.1
  - AWS Bedrock Claude 4.5 Sonnet
  - Azure OpenAI
  - Local LLMs (Ollama, vLLM, LocalAI)

#### 3. **API Analyzer** (Requires Cisco AI Defense API Key)
- Integration with Cisco AI Defense Inspect API
- Advanced threat detection and classification
- Cloud-based analysis with updated threat intelligence

### Comprehensive Scanning Capabilities

The scanner can analyze:

- **MCP Tools**: Scan tool definitions for security risks
- **MCP Prompts**: Detect prompt injection and manipulation risks
- **MCP Resources**: Analyze resource access patterns
- **Server Instructions**: Check initialization and configuration for security issues
- **Source Code**: Behavioral analysis of MCP server implementation
- **Static/Offline Files**: Scan pre-generated JSON files without live connections

### Multiple Scanning Modes

1. **Stdio Servers**: Scan local MCP servers launched via command-line
2. **HTTP/SSE Servers**: Scan remote MCP servers via HTTP endpoints
3. **Config File Scanning**: Scan all servers defined in MCP configuration files
4. **Well-Known Configs**: Auto-discover and scan servers from standard locations
5. **Static/Offline Mode**: CI/CD-friendly scanning of JSON artifacts

## Installation

The MCP Scanner is already installed in your project's virtual environment at:
```
/home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code/.venv
```

To verify installation:
```bash
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code
source .venv/bin/activate
pip show cisco-ai-mcp-scanner
```

## Security Threats Detected

The MCP Scanner uses the **AITech Threat Taxonomy** to classify security findings:

### High Severity Threats

- **Command Injection**: Execution of arbitrary system commands
- **Path Traversal**: Unauthorized file system access
- **Prompt Injection**: Manipulation of LLM behavior through prompts
- **Tool Poisoning**: Malicious tool definitions or behaviors
- **Data Exfiltration**: Unauthorized data extraction
- **Credential Exposure**: Hardcoded secrets or API keys

### Medium Severity Threats

- **Information Disclosure**: Unintended information leakage
- **Insufficient Input Validation**: Missing or weak input sanitization
- **Insecure Defaults**: Unsafe default configurations
- **Missing Authentication**: Lack of proper access controls

### Low Severity Threats

- **Verbose Error Messages**: Information leakage through errors
- **Missing Rate Limiting**: Potential for abuse
- **Weak Encryption**: Use of outdated cryptographic methods

## Using the Scanner

### Quick Start with CLI

The `mcp-scanner` command-line tool provides the fastest way to scan your servers:

```bash
# Scan your MCP config file with YARA (no API key needed)
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code
source .venv/bin/activate

mcp-scanner config \
  --config-path /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/.mcp.json \
  --analyzers yara \
  --format detailed
```

### Using the Custom Python Script

We've created a comprehensive Python script at:
```
/home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/scripts/python/scan_mcp_servers.py
```

**Important**: The script must be run from the `code` directory where the project dependencies are managed.

#### Basic Usage (YARA Only)

```bash
# Navigate to the code directory
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code

# Scan with default settings (YARA analyzer, default config path)
uv run python ../scripts/python/scan_mcp_servers.py
```

#### Advanced Usage (Multiple Analyzers)

```bash
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code

# Scan with YARA and LLM analyzers
export MCP_SCANNER_LLM_API_KEY="your_openai_api_key"
uv run python ../scripts/python/scan_mcp_servers.py --analyzers yara,llm

# Scan with all analyzers
export MCP_SCANNER_API_KEY="your_cisco_api_key"
export MCP_SCANNER_LLM_API_KEY="your_llm_api_key"
uv run python ../scripts/python/scan_mcp_servers.py --analyzers yara,llm,api
```

#### Custom Config and Output

```bash
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code

# Scan custom config and save to specific location
uv run python ../scripts/python/scan_mcp_servers.py \
  --config /path/to/custom/.mcp.json \
  --analyzers yara \
  --output /path/to/results.json
```

#### Command-Line Options

```
--config PATH          Path to MCP configuration file (default: .mcp.json in project root)
--analyzers LIST       Comma-separated analyzers: yara, llm, api (default: yara)
--output PATH          Path to save JSON results (default: scripts/python/mcp_scan_results.json)
--api-key KEY          Cisco AI Defense API key (for API analyzer)
--llm-api-key KEY      LLM provider API key (for LLM analyzer)
```

## Your MCP Configuration

Your `.mcp.json` file contains 6 configured servers:

### Stdio Servers (5)

1. **fetch** - `uvx mcp-server-fetch`
   - Web content fetching and processing

2. **filesystem** - `@modelcontextprotocol/server-filesystem`
   - Local file system access to project directory

3. **sequentialthinking** - `@modelcontextprotocol/server-sequential-thinking`
   - Structured reasoning capabilities

4. **context7** - `@upstash/context7-mcp`
   - Documentation search with Context7 API

5. **jupyter-mcp-server** - `uvx jupyter-mcp-server`
   - Jupyter notebook integration

### HTTP Servers (1)

6. **transcript-api** - `https://transcriptapi.com/mcp`
   - YouTube transcript retrieval
   - **Note**: Contains Bearer token in configuration

## Understanding Scan Results

### Console Output

The script provides real-time feedback:

```
================================================================================
🔒 MCP SERVER SECURITY SCANNER
================================================================================

Configuration: /home/user/.../.mcp.json
Analyzers: yara
Servers to scan: 6
================================================================================

📡 Scanning stdio server: fetch
   Command: uvx
   Args: ['mcp-server-fetch']
   ✅ Scanned 3 tools
      Safe: 2, Unsafe: 1

📡 Scanning stdio server: filesystem
   Command: npx
   Args: ['-y', '@modelcontextprotocol/server-filesystem', '/home/user/...']
   ✅ Scanned 12 tools
      Safe: 10, Unsafe: 2

...

================================================================================
📊 SCAN SUMMARY
================================================================================

Servers:
  Total:    6
  Scanned:  5
  Failed:   1

Tools:
  Total:    45
  ✅ Safe:    38
  ⚠️  Unsafe:  7

Findings:
  Total security findings: 14
```

### JSON Output

Results are saved in a structured JSON format:

```json
{
  "scan_timestamp": "2026-02-06T...",
  "config_file": "/home/user/.../.mcp.json",
  "analyzers_used": ["yara"],
  "servers": {
    "fetch": {
      "server_type": "stdio",
      "status": "completed",
      "tools": [
        {
          "name": "fetch",
          "description": "Fetches a URL from the internet...",
          "is_safe": true,
          "status": "completed",
          "findings": [],
          "analyzer_results": {
            "yara": {
              "is_safe": true,
              "findings_count": 0
            }
          }
        }
      ]
    }
  },
  "summary": {
    "total_servers": 6,
    "scanned_servers": 5,
    "total_tools": 45,
    "safe_tools": 38,
    "unsafe_tools": 7,
    "total_findings": 14
  }
}
```

## Security Recommendations

### 1. Regular Scanning

Run security scans:
- **Before deployment**: Scan new MCP servers before adding them to production
- **Weekly**: Automated scans of your MCP configuration
- **After updates**: Scan when MCP server packages are updated
- **CI/CD integration**: Add scanning to your continuous integration pipeline

### 2. Analyzer Selection

- **Development**: Use YARA for fast feedback
- **Pre-production**: Use YARA + LLM for comprehensive analysis
- **Production**: Use all three analyzers for maximum coverage

### 3. Addressing Findings

When the scanner reports unsafe tools:

1. **Review the findings**: Understand what triggered the detection
2. **Check tool documentation**: Verify if the behavior is intentional
3. **Update or replace**: Update to newer versions or find safer alternatives
4. **Request whitelisting**: For known-safe patterns, consider custom YARA rules
5. **Monitor closely**: If a risk must be accepted, implement additional monitoring

### 4. Secure Configuration

- **Remove unused servers**: Disable MCP servers you don't actively use
- **Limit file system access**: Restrict filesystem server to specific directories
- **Rotate credentials**: Regularly update API tokens and bearer tokens
- **Use environment variables**: Don't hardcode sensitive values in config files
- **Enable authentication**: Use OAuth or bearer tokens for remote servers

### 5. Bearer Token Security

Your `transcript-api` server has a bearer token in the config file:

```json
{
  "headers": {
    "Authorization": "Bearer sk_YOUR_TRANSCRIPT_API_KEY_HERE"
  }
}
```

**Recommendations**:
- Move this token to an environment variable
- Add `.mcp.json` to `.gitignore` if not already present
- Rotate the token if this file has been committed to version control
- Use token expiration/rotation policies

Example secure configuration:
```json
{
  "transcript-api": {
    "type": "http",
    "url": "https://transcriptapi.com/mcp",
    "headers": {
      "Authorization": "Bearer ${TRANSCRIPT_API_TOKEN}"
    }
  }
}
```

## Additional Resources

### Official Documentation

- [MCP Scanner GitHub](https://github.com/cisco-ai-defense/mcp-scanner)
- [Architecture Guide](https://github.com/cisco-ai-defense/mcp-scanner/tree/main/docs/architecture.md)
- [MCP Threats Taxonomy](https://github.com/cisco-ai-defense/mcp-scanner/tree/main/docs/mcp-threats-taxonomy.md)
- [LLM Providers Configuration](https://github.com/cisco-ai-defense/mcp-scanner/tree/main/docs/llm-providers.md)
- [API Reference](https://github.com/cisco-ai-defense/mcp-scanner/tree/main/docs/api-reference.md)

### Cisco AI Defense

- [Cisco AI Defense Product Page](https://www.cisco.com/site/us/en/products/security/ai-defense/index.html)
- [AI Security and Safety Framework](https://learn-cloudsecurity.cisco.com/ai-security-framework)

### Community

- [Discord Server](https://discord.com/invite/nKWtDcXxtx) - Join the community for support and discussions

## Troubleshooting

### Common Issues

#### 1. Server Connection Failures

**Symptom**: `❌ Scan failed: Connection refused` or timeout errors

**Solutions**:
- For stdio servers: Ensure the command is available in PATH
- For HTTP servers: Verify the server is running and accessible
- Check network connectivity and firewall rules
- Verify authentication tokens are valid

#### 2. Missing Dependencies

**Symptom**: `ModuleNotFoundError: No module named 'mcpscanner'`

**Solution**:
```bash
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer/code
source .venv/bin/activate
uv pip install cisco-ai-mcp-scanner
```

#### 3. LLM Analyzer Errors

**Symptom**: `LLM analyzer failed: API key not configured`

**Solution**:
```bash
# For OpenAI
export MCP_SCANNER_LLM_API_KEY="sk-..."
export MCP_SCANNER_LLM_MODEL="gpt-4o"

# For AWS Bedrock
export AWS_PROFILE="your-profile"
export AWS_REGION="us-east-1"
export MCP_SCANNER_LLM_MODEL="bedrock/anthropic.claude-sonnet-4-5-20250929-v2:0"
```

#### 4. Permission Errors

**Symptom**: `PermissionError: [Errno 13] Permission denied`

**Solution**:
- Make sure the script is executable: `chmod +x scripts/python/scan_mcp_servers.py`
- Check file permissions on the config file and output directory
- Run with appropriate user permissions

### Getting Help

1. **Check the logs**: Review the detailed error messages in the console output
2. **Inspect JSON results**: The `mcp_scan_results.json` file contains detailed error information
3. **GitHub Issues**: Report bugs at [mcp-scanner/issues](https://github.com/cisco-ai-defense/mcp-scanner/issues)
4. **Discord Community**: Ask questions in the Discord server
5. **Documentation**: Review the official docs linked above

## Example Workflow

Here's a complete security scanning workflow:

```bash
#!/bin/bash
# MCP Security Scan Workflow

# 1. Set up environment
cd /home/user/jeffrymahbuubi/PROJECTS/7-LibreVNA-Vector-Network-Analyzer
export SCAN_DATE=$(date +%Y%m%d)
export RESULTS_DIR="scripts/python/scan_results_${SCAN_DATE}"
mkdir -p "${RESULTS_DIR}"

# 2. Run YARA scan (fast, no API key needed)
echo "Running YARA scan..."
uv run python scripts/python/scan_mcp_servers.py \
  --analyzers yara \
  --output "${RESULTS_DIR}/yara_results.json"

# 3. If critical issues found, run LLM scan for deeper analysis
if grep -q '"unsafe_tools": [1-9]' "${RESULTS_DIR}/yara_results.json"; then
  echo "Unsafe tools detected. Running LLM analysis..."

  # Configure LLM (example with OpenAI)
  export MCP_SCANNER_LLM_API_KEY="${OPENAI_API_KEY}"

  uv run python scripts/python/scan_mcp_servers.py \
    --analyzers llm \
    --output "${RESULTS_DIR}/llm_results.json"
fi

# 4. Generate summary report
echo "Scan complete. Results in ${RESULTS_DIR}/"
ls -lh "${RESULTS_DIR}/"
```

## Conclusion

The MCP Scanner is a powerful tool for ensuring the security of your MCP infrastructure. By integrating security scanning into your development workflow, you can:

- **Detect threats early**: Find security issues before they reach production
- **Maintain compliance**: Document security posture with detailed scan reports
- **Reduce risk**: Identify and remediate vulnerabilities proactively
- **Build confidence**: Deploy MCP servers knowing they've been thoroughly analyzed

Start with YARA-based scanning for quick feedback, then layer in LLM and API analyzers for comprehensive protection.

---

**Last Updated**: 2026-02-06
**Script Version**: 1.0
**MCP Scanner Version**: Latest (cisco-ai-mcp-scanner)
