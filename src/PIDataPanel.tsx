/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: LicenseRef-NvidiaProprietary
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */
import React from 'react';
import './App.css';
import './PIDataPanel.css';

interface PIDataValue {
    name: string;
    value: number | string;
    unit: string;
    timestamp: string;
}

interface PIDataState {
    values: PIDataValue[];
    isLoading: boolean;
    error: string | null;
    lastUpdated: string | null;
}

interface PIDataPanelProps {
    width: number;
    piData: PIDataState;
    onClose: () => void;
    onRefresh: () => void;
    selectedObjectPath: string;
}

export default class PIDataPanel extends React.Component<PIDataPanelProps> {
    
    /**
     * Format timestamp for display
     */
    private _formatTimestamp(timestamp: string): string {
        try {
            const date = new Date(timestamp);
            return date.toLocaleTimeString();
        } catch {
            return timestamp;
        }
    }

    /**
     * Format value for display
     */
    private _formatValue(value: number | string): string {
        if (typeof value === 'number') {
            return value.toFixed(2);
        }
        return String(value);
    }

    /**
     * Get status color based on value
     */
    private _getValueColor(name: string, value: number | string): string {
        if (value === "N/A" || value === "") {
            return '#888888';
        }

        // Temperature ranges
        if (name.toLowerCase().includes('temp') && typeof value === 'number') {
            if (value < 0) return '#0099ff';      // Very cold - blue
            if (value < 20) return '#66ccff';     // Cold - light blue
            if (value < 30) return '#00cc66';     // Normal - green
            if (value < 50) return '#ffcc00';     // Warm - yellow
            if (value < 80) return '#ff9900';     // Hot - orange
            return '#ff3300';                     // Very hot - red
        }

        // Power/Current ranges
        if ((name.toLowerCase().includes('power') || name.toLowerCase().includes('current')) && typeof value === 'number') {
            if (value === 0) return '#888888';    // Off - gray
            if (value < 50) return '#00cc66';     // Low - green
            if (value < 100) return '#ffcc00';    // Medium - yellow
            return '#ff9900';                     // High - orange
        }

        // Default color
        return '#ffffff';
    }

    /**
     * Render individual PI data value
     */
    private _renderDataValue(data: PIDataValue, index: number): JSX.Element {
        const valueColor = this._getValueColor(data.name, data.value);
        
        return (
            <div key={index} className="pi-data-row">
                <div className="pi-data-label">
                    {data.name}
                </div>
                <div className="pi-data-value" style={{ color: valueColor }}>
                    {this._formatValue(data.value)} {data.unit}
                </div>
            </div>
        );
    }

    /**
     * Render error state
     */
    private _renderError(): JSX.Element {
        return (
            <div className="pi-data-error">
                <div className="pi-error-icon">⚠️</div>
                <div className="pi-error-message">
                    {this.props.piData.error}
                </div>
                <button 
                    className="nvidia-button pi-retry-button"
                    onClick={this.props.onRefresh}
                >
                    Retry
                </button>
            </div>
        );
    }

    /**
     * Render loading state
     */
    private _renderLoading(): JSX.Element {
        return (
            <div className="pi-data-loading">
                <div className="spinner-border" role="status" />
                <div className="pi-loading-text">
                    Fetching PI data...
                </div>
            </div>
        );
    }

    /**
     * Render empty state
     */
    private _renderEmpty(): JSX.Element {
        return (
            <div className="pi-data-empty">
                <div className="pi-empty-icon">📊</div>
                <div className="pi-empty-message">
                    No PI data available
                </div>
            </div>
        );
    }

    render() {
        const { piData, width, selectedObjectPath, onClose, onRefresh } = this.props;

        return (
            <div className="pi-data-panel" style={{ width: width }}>
                {/* Header */}
                <div className="pi-data-header">
                    <div className="pi-data-title">
                        PI System Data
                    </div>
                    <button 
                        className="pi-close-button"
                        onClick={onClose}
                        title="Close PI Data Panel"
                    >
                        ×
                    </button>
                </div>

                {/* Object info */}
                <div className="pi-object-info">
                    <div className="pi-object-label">Selected Object:</div>
                    <div className="pi-object-path">Door Panel</div>
                </div>

                {/* Controls */}
                <div className="pi-controls">
                    <button 
                        className="nvidia-button pi-refresh-button"
                        onClick={onRefresh}
                        disabled={piData.isLoading}
                    >
                        🔄 Refresh
                    </button>
                    {piData.lastUpdated && (
                        <div className="pi-last-updated">
                            Last updated: {this._formatTimestamp(piData.lastUpdated)}
                        </div>
                    )}
                </div>

                {/* Content */}
                <div className="pi-data-content">
                    {piData.isLoading && this._renderLoading()}
                    
                    {piData.error && !piData.isLoading && this._renderError()}
                    
                    {!piData.isLoading && !piData.error && piData.values.length === 0 && this._renderEmpty()}
                    
                    {!piData.isLoading && !piData.error && piData.values.length > 0 && (
                        <div className="pi-data-list">
                            {piData.values.map((data, index) => this._renderDataValue(data, index))}
                        </div>
                    )}
                </div>
            </div>
        );
    }
}