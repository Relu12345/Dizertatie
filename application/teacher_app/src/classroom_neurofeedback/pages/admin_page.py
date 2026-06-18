from __future__ import annotations

import pandas as pd
import streamlit as st

from classroom_neurofeedback.services.admin_store import (
    change_pin,
    deploy_to_device,
    deployment_command,
    deployment_logs,
    discover_devices,
    list_devices,
    load_admin_config,
    merge_discovered_devices,
    save_devices,
    save_network_settings,
    verify_pin,
)
from classroom_neurofeedback.services.collector_service import get_collector
from classroom_neurofeedback.ui.common import safe, section_head
from classroom_neurofeedback.pages.live_streams_page import render_live_stream_cards


def render_admin_page() -> None:
    section_head("Admin Setup")
    if not st.session_state.get("admin_unlocked"):
        _render_pin_gate()
        return

    config = load_admin_config()
    st.caption("IT console for Raspberry Pi nodes, headset assignments, and Pi runtime deployment.")

    overview_tab, inventory_tab, deployment_tab, live_tab, security_tab = st.tabs(
        ["Overview", "Pi Inventory", "Deploy Runtime", "Live Streams", "Security"]
    )
    with overview_tab:
        _render_overview(config)
    with inventory_tab:
        _render_inventory(config)
    with deployment_tab:
        _render_deployment(config)
    with live_tab:
        _render_live_stream_admin()
    with security_tab:
        _render_security()


def _render_pin_gate() -> None:
    st.markdown(
        """
        <article class='ui-card'>
            <div class='ui-card-title'>Admin Access</div>
            <div class='ui-card-meta'>
                Enter the local admin PIN to manage Raspberry Pi nodes and deployment settings.
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )
    with st.form("admin_pin_form"):
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Unlock Admin Console", width="stretch")
    if submitted:
        if verify_pin(pin):
            st.session_state["admin_unlocked"] = True
            st.rerun()
        else:
            st.error("Incorrect PIN.")


def _render_overview(config: dict) -> None:
    devices = list_devices()
    enabled = [device for device in devices if device.get("enabled", True)]
    online = [device for device in devices if device.get("status") == "Online"]
    deployed = [log for log in deployment_logs() if log.get("success")]

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Managed Pis", len(devices))
    col_b.metric("Enabled", len(enabled))
    col_c.metric("Online Last Scan", len(online))
    col_d.metric("Successful Deploys", len(deployed))

    st.markdown(
        f"""
        <article class='ui-card'>
            <div class='ui-card-title'>Recommended IT Flow</div>
            <div class='ui-card-meta'>
                1. Scan hostnames from {safe(config["host_prefix"])}{safe(config["scan_start"])}
                to {safe(config["host_prefix"])}{safe(config["scan_end"])}.<br>
                2. Assign each Pi to a headset and optional student label.<br>
                3. Deploy the Pi runtime with user {safe(config["username"])}.<br>
                4. Start acquisition on each Pi, then confirm LSL streams from Live Streams.
            </div>
        </article>
        """,
        unsafe_allow_html=True,
    )

    logs = deployment_logs()
    if logs:
        st.markdown("#### Recent Deployment Activity")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Pi": log["hostname"],
                        "Result": "OK" if log["success"] else "Failed",
                        "Finished": log["finished_at"],
                    }
                    for log in logs[:8]
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def _render_inventory(config: dict) -> None:
    st.markdown("#### Network Scan")
    with st.form("admin_network_settings"):
        col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 2])
        host_prefix = col_a.text_input("Hostname prefix", value=config["host_prefix"])
        scan_start = col_b.number_input("From", min_value=1, max_value=999, value=int(config["scan_start"]), step=1)
        scan_end = col_c.number_input("To", min_value=1, max_value=999, value=int(config["scan_end"]), step=1)
        username = col_d.text_input("SSH username", value=config["username"])
        remote_dir = st.text_input("Remote runtime directory", value=config["remote_dir"])
        save_settings = st.form_submit_button("Save Scan Settings", width="stretch")
    if save_settings:
        save_network_settings(host_prefix, int(scan_start), int(scan_end), username, remote_dir)
        st.success("Admin scan settings saved.")
        st.rerun()

    scan_col, merge_col = st.columns(2)
    if scan_col.button("Scan Pi Hostnames", width="stretch"):
        with st.spinner("Resolving and pinging Pi hostnames..."):
            st.session_state["admin_discovered_devices"] = discover_devices(
                config["host_prefix"],
                int(config["scan_start"]),
                int(config["scan_end"]),
            )
    discovered = st.session_state.get("admin_discovered_devices", [])
    if discovered:
        st.dataframe(pd.DataFrame(discovered), hide_index=True, width="stretch")
        if merge_col.button("Merge Scan Into Inventory", width="stretch"):
            merge_discovered_devices(discovered)
            st.success("Inventory updated from scan results.")
            st.rerun()

    st.markdown("#### Managed Devices")
    devices = list_devices()
    if not devices:
        devices = [
            {
                "hostname": "relu-pi-1",
                "ip": "",
                "headset": "Unicorn-1",
                "student": "",
                "status": "Unknown",
                "notes": "Edit this starter row or scan the network.",
                "enabled": True,
                "sort": 1,
            }
        ]

    edited = st.data_editor(
        pd.DataFrame(devices),
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "enabled": st.column_config.CheckboxColumn("Enabled"),
            "sort": st.column_config.NumberColumn("Order", min_value=1, step=1),
            "hostname": st.column_config.TextColumn("Hostname", required=True),
            "ip": st.column_config.TextColumn("IP"),
            "headset": st.column_config.TextColumn("Headset"),
            "student": st.column_config.TextColumn("Student"),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["Unknown", "Online", "Resolved", "Not found", "Needs deploy", "Ready"],
            ),
            "notes": st.column_config.TextColumn("Notes"),
        },
        key="admin_device_editor",
    )
    if st.button("Save Device Inventory", width="stretch"):
        save_devices(edited.fillna("").to_dict("records"))
        st.success("Device inventory saved.")
        st.rerun()


def _render_deployment(config: dict) -> None:
    devices = [device for device in list_devices() if device.get("enabled", True)]
    if not devices:
        st.info("Add or scan devices in Pi Inventory before deploying.")
        return

    labels = [f"{device['hostname']} ({device.get('headset') or 'no headset'})" for device in devices]
    selected_labels = st.multiselect("Deploy to", options=labels, default=labels[:1])
    selected_devices = [devices[labels.index(label)] for label in selected_labels]
    skip_install = st.checkbox("Skip Python/liblsl dependency install", value=False)

    st.markdown("#### Command Preview")
    if selected_devices:
        commands = [
            deployment_command(device["hostname"], config["username"], config["remote_dir"], skip_install)
            for device in selected_devices
        ]
        st.code("\n".join(commands), language="powershell")

    deploy_col, start_col = st.columns(2)
    if deploy_col.button("Deploy Runtime To Selected Pis", width="stretch", disabled=not selected_devices):
        for device in selected_devices:
            with st.spinner(f"Deploying to {device['hostname']}..."):
                log = deploy_to_device(device["hostname"], config["username"], config["remote_dir"], skip_install)
            if log["success"]:
                st.success(f"{device['hostname']}: deployment complete.")
            else:
                st.error(f"{device['hostname']}: deployment failed.")
                st.code(log["output"] or "No output.", language="text")

    if start_col.button("Show Start Commands", width="stretch", disabled=not selected_devices):
        commands = [
            (
                f"ssh {config['username']}@{device['hostname']} "
                f"\"cd {config['remote_dir']} && . .venv/bin/activate && "
                "python3 stream_unicorn_lsl.py --lsl-name Unicorn --single-channel --channel-name 'EEG 1'\""
            )
            for device in selected_devices
        ]
        st.code("\n".join(commands), language="bash")

    logs = deployment_logs()
    if logs:
        st.markdown("#### Deployment Logs")
        selected_log = st.selectbox(
            "View log",
            options=list(range(len(logs))),
            format_func=lambda index: f"{logs[index]['hostname']} - {'OK' if logs[index]['success'] else 'Failed'} - {logs[index]['finished_at']}",
        )
        st.code(logs[selected_log].get("output") or "No output.", language="text")


def _render_live_stream_admin() -> None:
    st.markdown("#### Live Stream Validation")
    st.caption("Use this after deployment to confirm that the Pi nodes are publishing LSL streams.")
    collector = get_collector()
    if st.button("Force LSL Discovery", width="stretch"):
        collector.force_discovery()
    render_live_stream_cards(collector)


def _render_security() -> None:
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### Change Admin PIN")
        with st.form("change_admin_pin"):
            old_pin = st.text_input("Current PIN", type="password")
            new_pin = st.text_input("New PIN", type="password")
            confirm_pin = st.text_input("Confirm new PIN", type="password")
            submitted = st.form_submit_button("Change PIN", width="stretch")
        if submitted:
            if new_pin != confirm_pin:
                st.error("The new PIN fields do not match.")
            else:
                ok, message = change_pin(old_pin, new_pin)
                if ok:
                    st.success(message)
                else:
                    st.error(message)

    with col_b:
        st.markdown("#### Session")
        st.caption("The default PIN is 2002 until it is changed here.")
        if st.button("Lock Admin Console", width="stretch"):
            st.session_state["admin_unlocked"] = False
            st.rerun()
