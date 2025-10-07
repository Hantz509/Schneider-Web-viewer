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
import AppStream from './AppStream'; // Ensure .tsx extension if needed
import StreamConfig from '../stream.config.json';
import USDAsset from "./USDAsset";
import USDStage from "./USDStage";
import PIDataPanel from "./PIDataPanel"; // Import PI Data Panel
import { headerHeight } from './App';

 
interface USDAssetType {
    name: string;
    url: string;
}

interface USDPrimType {
    name?: string;
    path: string;
    children?: USDPrimType[];
}

// PI Data interfaces
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

export interface AppProps {
    sessionId: string
    backendUrl: string
    signalingserver: string
    signalingport: number
    mediaserver: string
    mediaport: number
    accessToken: string
    onStreamFailed: () => void;
}

interface AppState {
    usdAssets: USDAssetType[];
    selectedUSDAsset: USDAssetType;
    usdPrims: USDPrimType[];
    selectedUSDPrims: Set<USDPrimType>;
    isKitReady: boolean;
    showStream: boolean;
    showUI: boolean;
    isLoading: boolean;
    loadingText: string; 
    selectedCamera: string;
    // PI Data related state
    piData: PIDataState;
    showPiPanel: boolean;
    selectedObjectPath: string;
}

interface AppStreamMessageType {
    event_type: string;
    payload: any;
}

// Camera Selector Component - UPDATED WITH FREE CAMERA
interface CameraSelectorProps {
    visible: boolean;
    onCameraSelect: (cameraPath: string) => void;
    selectedCamera: string;
}

interface CameraSelectorState {
    selectedCamera: string;
}

class CameraSelector extends React.Component<CameraSelectorProps, CameraSelectorState> {
    private cameras = [
        { name: "Free Camera", path: "" }, // NEW: Free navigation mode
        { name: "P5A", path: "/World/MEP____/Cameras/P5A" },
        { name: "P5B", path: "/World/MEP____/Cameras/P5B" },
        { name: "P5C", path: "/World/MEP____/Cameras/P5C" },
        { name: "P5D", path: "/World/MEP____/Cameras/P5D" }
    ];

    constructor(props: CameraSelectorProps) {
        super(props);
        this.state = {
            selectedCamera: props.selectedCamera || this.cameras[0].path
        };
    }

    componentDidUpdate(prevProps: CameraSelectorProps) {
        if (prevProps.selectedCamera !== this.props.selectedCamera) {
            this.setState({ selectedCamera: this.props.selectedCamera });
        }
    }

    handleCameraChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
        const selectedPath = event.target.value;
        this.setState({ selectedCamera: selectedPath });
        
        if (selectedPath === "") {
            // Free camera mode - send special message
            this.props.onCameraSelect("FREE_CAMERA");
        } else {
            // Fixed camera mode
            this.props.onCameraSelect(selectedPath);
        }
    };

    render() {
        if (!this.props.visible) return null;

        return (
            <div className="camera-selector-container" style={{ 
                position: 'absolute', 
                top: '10px', 
                right: '320px', 
                zIndex: 1000,
                backgroundColor: 'rgba(0,0,0,0.8)',
                padding: '10px',
                borderRadius: '5px'
            }}>
                <label style={{ color: 'white', marginRight: '10px' }}>Camera View:</label>
                <select 
                    className="nvidia-dropdown"
                    value={this.state.selectedCamera}
                    onChange={this.handleCameraChange}
                >
                    {this.cameras.map(camera => (
                        <option key={camera.path || "free"} value={camera.path}>
                            {camera.name}
                        </option>
                    ))}
                </select>
            </div>
        );
    }
}

export default class App extends React.Component<AppProps, AppState> {
    
    private usdStageRef = React.createRef<USDStage>();
    
    constructor(props: AppProps) {
        super(props);
        
        // list of selectable USD assets - UPDATED WITH MEP_SCHNEIDER
        const usdAssets: USDAssetType[] = StreamConfig.source === "stream"? [
            
            {name: "MEP_Schneider", url: "C:/web-viewer-sample/public/samples/MEP_Schneider/MEP_Schneider/MEP_Schneider.usd"}
        ]
        :
        [
           
            {name: "MEP_Schneider", url: "./samples/MEP_Schneider/MEP_Schneider/MEP_Schneider.usd"}
        ];

        this.state = {
            usdAssets: usdAssets,
            selectedUSDAsset: usdAssets[0],
            usdPrims: [],
            selectedUSDPrims: new Set<USDPrimType>(),
            isKitReady: false,
            showStream: false,
            showUI: false,
            loadingText: StreamConfig.source === "gfn" ? "Log in to GeForce NOW to view stream" : (StreamConfig.source === "stream" ? "Waiting for stream to initialize":  "Waiting for stream to begin"),
            isLoading: StreamConfig.source === "stream" ? true : false,
            selectedCamera: "", // UPDATED: Start with free camera mode
            // PI Data state
            piData: {
                values: [],
                isLoading: false,
                error: null,
                lastUpdated: null
            },
            showPiPanel: false,
            selectedObjectPath: ""
        }
    }

    /**
     * PI Web API Configuration
     */
    private readonly PI_CONFIG = {
        // Using local proxy server to avoid CORS issues
        attributesUrl: "http://localhost:3001/api/pi/attributes",
        valueUrlBase: "http://localhost:3001/api/pi/value/"
    };

    /**
     * Mapping of PI attribute names to display information
     */
    private readonly PI_ATTRIBUTE_MAP = {
        "temperature": { label: "Temp 01", unit: "°C" },
        "TemperatureSetpoint": { label: "Temp 02", unit: "°C" },
        "PowerUsage": { label: "Temp 03", unit: "°C" },
        "Current": { label: "Temp 04", unit: "°C" },
        "internalCalculOutput": { label: "Temp 05", unit: "" },
        "temp_06": { label: "Temp 06", unit: "°C" },
        "temp_07": { label: "Temp 07", unit: "°C" },
        "temp_08": { label: "Temp 08", unit: "°C" },
        "temp_09": { label: "Temp 09", unit: "°C" },
        "temp_10": { label: "Temp 10", unit: "°C" },
        "temp_11": { label: "Temp 11", unit: "°C" }
    };

    /**
     * Fetch PI data from the PI Web API via proxy server
     */
    private async _fetchPIData(): Promise<void> {
        console.log('*** FETCHING REAL PI DATA VIA PROXY ***');
        
        this.setState(prevState => ({
            piData: {
                ...prevState.piData,
                isLoading: true,
                error: null
            }
        }));

        try {
            console.log('Making request to proxy server:', this.PI_CONFIG.attributesUrl);
            
            // Fetch attributes from proxy server
            const attributesResponse = await fetch(this.PI_CONFIG.attributesUrl, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!attributesResponse.ok) {
                throw new Error(`Proxy server error: ${attributesResponse.status} ${attributesResponse.statusText}`);
            }

            const attributesData = await attributesResponse.json();
            console.log('PI Attributes received from proxy:', attributesData);
            
            const attributes = attributesData.Items || [];

            // Create a map of attribute names to WebIds
            const attributeMap = attributes.reduce((map: any, attr: any) => {
                map[attr.Name] = attr.WebId;
                return map;
            }, {});

            console.log('Available PI attributes:', Object.keys(attributeMap));

            // Fetch values for each attribute we're interested in
            const piValues: PIDataValue[] = [];
            const timestamp = new Date().toLocaleString();

            for (const [attrName, config] of Object.entries(this.PI_ATTRIBUTE_MAP)) {
                if (attributeMap[attrName]) {
                    try {
                        console.log(`Fetching value for ${attrName} via proxy...`);
                        const valueResponse = await fetch(
                            `${this.PI_CONFIG.valueUrlBase}${encodeURIComponent(attributeMap[attrName])}`,
                            {
                                method: 'GET',
                                headers: {
                                    'Content-Type': 'application/json'
                                }
                            }
                        );

                        if (valueResponse.ok) {
                            const valueData = await valueResponse.json();
                            console.log(`${attrName} value from proxy:`, valueData);
                            
                            piValues.push({
                                name: config.label,
                                value: typeof valueData.Value === 'number' ? 
                                       Math.round(valueData.Value * 100) / 100 : 
                                       valueData.Value,
                                unit: config.unit,
                                timestamp: valueData.Timestamp || timestamp
                            });
                        } else {
                            console.warn(`Failed to fetch value for ${attrName}: ${valueResponse.status}`);
                            piValues.push({
                                name: config.label,
                                value: "Error",
                                unit: config.unit,
                                timestamp: timestamp
                            });
                        }
                    } catch (error) {
                        console.error(`Error fetching value for ${attrName}:`, error);
                        piValues.push({
                            name: config.label,
                            value: "N/A",
                            unit: config.unit,
                            timestamp: timestamp
                        });
                    }
                } else {
                    console.warn(`Attribute ${attrName} not found in PI system`);
                    piValues.push({
                        name: config.label,
                        value: "Not Found",
                        unit: config.unit,
                        timestamp: timestamp
                    });
                }
            }

            console.log('*** REAL PI DATA FETCHED VIA PROXY ***', piValues);

            this.setState(prevState => ({
                piData: {
                    values: piValues,
                    isLoading: false,
                    error: null,
                    lastUpdated: timestamp
                }
            }));

        } catch (error) {
            console.error('PI Data fetch error via proxy:', error);
            
            // Create fallback test data if real data fails
            const piValues: PIDataValue[] = [];
            const timestamp = new Date().toLocaleString();

            for (const [attrName, config] of Object.entries(this.PI_ATTRIBUTE_MAP)) {
                piValues.push({
                    name: config.label,
                    value: "Connection Failed",
                    unit: config.unit,
                    timestamp: timestamp
                });
            }

            this.setState(prevState => ({
                piData: {
                    values: piValues,
                    isLoading: false,
                    error: `Failed to connect to PI Web API via proxy: ${error instanceof Error ? error.message : 'Unknown error'}`,
                    lastUpdated: timestamp
                }
            }));
        }
    }

    /**
     * Handle closing the PI data panel
     */
    private _closePIPanel = (): void => {
        this.setState({ 
            showPiPanel: false,
            selectedObjectPath: ""
        });
    }

    /**
     * Handle refresh PI data
     */
    private _refreshPIData = (): void => {
        if (this.state.showPiPanel) {
            this._fetchPIData();
        }
    }

    /**
     * Check if currently in one of the P5 camera views
     */
    private _isInP5CameraView(): boolean {
        const p5Cameras = [
            "/World/MEP____/Cameras/P5A",
            "/World/MEP____/Cameras/P5B", 
            "/World/MEP____/Cameras/P5C",
            "/World/MEP____/Cameras/P5D"
        ];
        return p5Cameras.includes(this.state.selectedCamera);
    }

    /**
    * @function _queryLoadingState
    *
    * Sends Kit a message to find out what the loading state is.
    * Receives a 'loadingStateResponse' event type
    */
    private _queryLoadingState(): void {
        const message: AppStreamMessageType = {
            event_type: "loadingStateQuery",
            payload: {}
        };
        AppStream.sendMessage(JSON.stringify(message));
    }

    /**
     * @function _onStreamStarted
     *
     * Sends a request to open an asset. If the stream is from GDN it is assumed that the
     * application will automatically load an asset on startup so a request to open a stage
     * is not sent. Instead, we wait for the streamed application to send a
     * openedStageResult message.
     */
        private _onStreamStarted(): void {
            this._pollForKitReady()
        }

    /**
    * @function _pollForKitReady
    *
    * Attempts to query Kit's loading state until a response is received.
    * Once received, the 'isKitReady' flag is set to true and polling ends
    */
    async _pollForKitReady() {
        if (this.state.isKitReady === true) return

        console.info("polling Kit availability")
        this._queryLoadingState()
        setTimeout(() => this._pollForKitReady(), 3000); // Poll every 3 seconds
    }
    
    /**
     * @function _getAsset
     * 
     * Attempts to retrieve an asset from the list of USD assets based on a supplied USD path
     * If a match is not found, a USDAssetType with empty values is returned.
     */
    private _getAsset(path: string): USDAssetType {
        if (!path)
            return {name: "", url: ""}
        
        // returns the file name from a path
        const getFileNameFromPath = (path: string): string | undefined => path.split(/[/\\]/).pop();

        for (const asset of this.state.usdAssets) {
            if (getFileNameFromPath(asset.url) === getFileNameFromPath(path))
                return asset
        }
        
        return {name: "", url: ""}
    }

    /**
    * @function _onLoggedIn
    *
    * Runs when the user logs in
    */
    private _onLoggedIn(userId: string): void {
        if (StreamConfig.source === "gfn"){
            console.info(`Logged in to GeForce NOW as ${userId}`)
            this.setState({ loadingText: "Waiting for stream to begin", isLoading: false})
        }
    }

    /**
    * @function _openSelectedAsset
    *
    * Send a request to load an asset based on the currently selected asset
    */
    private _openSelectedAsset(): void {
        this.setState({ loadingText: "Loading Asset...", showStream: false, isLoading: true })
        this.setState({ usdPrims: [], selectedUSDPrims: new Set<USDPrimType>() });
        this.usdStageRef.current?.resetExpandedIds();
        console.log(`Sending request to open asset: ${this.state.selectedUSDAsset.url}.`);
        const message: AppStreamMessageType = {
            event_type: "openStageRequest",
            payload: {
                url: this.state.selectedUSDAsset.url
            }
        };
        AppStream.sendMessage(JSON.stringify(message));
    }

    /**
    * @function _onSelectUSDAsset
    *
    * React to user selecting an asset in the USDAsset selector.
    */
    private _onSelectUSDAsset (usdAsset: USDAssetType): void {
        console.log(`Asset selected: ${usdAsset.name}.`);
        this.setState({ selectedUSDAsset: usdAsset }, () => {
            this._openSelectedAsset();
        });
    }
    
    /**
    * @function _getChildren
    *
    * Send a request for the child prims of the given usdPrim.
    * Note that a filter is supported.
    */
    private _getChildren (usdPrim: USDPrimType | null = null): void {
        // Get geometry prims. If no usdPrim is specified then get children of /World.
        console.log(`Requesting children for path: ${usdPrim ? usdPrim.path : '/World'}.`);
        const message: AppStreamMessageType = {
            event_type: "getChildrenRequest",
            payload: {
                prim_path   : usdPrim ? usdPrim.path : '/World',
                filters     : ['USDGeom']
            }
        };
        AppStream.sendMessage(JSON.stringify(message));
    }

    /**
    * @function _makePickable
    *
    * Send a request to make prims pickable/selectable.
    * By default the client requests to make only a handful of the prims selectable - leaving the background items unselectable.
    */
    private _makePickable (usdPrims: USDPrimType[]): void {
        const paths: string[] = usdPrims.map(prim => prim.path);
        console.log(`Sending request to make prims pickable: ${paths}.`);
        const message: AppStreamMessageType = {
            event_type: "makePrimsPickable",
            payload: {
                paths   : paths,
            }
        };
        AppStream.sendMessage(JSON.stringify(message));
    }

    /**
     * @function _switchCamera
     * 
     * UPDATED: Send a request to switch to a specific camera view or free camera
     */
    private _switchCamera(cameraPath: string): void {
        console.log(`Switching to camera: ${cameraPath}`);
        this.setState({ selectedCamera: cameraPath === "FREE_CAMERA" ? "" : cameraPath });
        const message: AppStreamMessageType = {
            event_type: "switchCameraRequest",
            payload: {
                camera_path: cameraPath
            }
        };
        AppStream.sendMessage(JSON.stringify(message));
    }

    /**
     * @function _isMEPSchneiderAsset
     * 
     * Check if the currently selected asset is the MEP_Schneider file
     */
    private _isMEPSchneiderAsset(): boolean {
        return this.state.selectedUSDAsset?.name === "MEP_Schneider";
    }

    /**
    * @function _onSelectUSDPrims
    *
    * React to user selecting items in the USDStage list.
    * For MEP_Schneider, handle camera switching when cameras are selected.
    */
    private _onSelectUSDPrims (selectedUsdPrims: Set<USDPrimType>): void {
        console.log(`Sending request to select: ${Array.from(selectedUsdPrims).map(p => p.path)}`);
        this.setState({ selectedUSDPrims: selectedUsdPrims });
        
        // Check if this is MEP_Schneider and if a camera was selected
        if (this._isMEPSchneiderAsset() && selectedUsdPrims.size === 1) {
            const selectedPrim = Array.from(selectedUsdPrims)[0];
            const cameraNames = ['P5A', 'P5B', 'P5C', 'P5D'];
            
            // Check if the selected prim is one of our cameras
            if (cameraNames.some(name => selectedPrim.path.includes(name))) {
                // Extract camera name and switch to it
                const cameraName = cameraNames.find(name => selectedPrim.path.includes(name));
                if (cameraName) {
                    this._switchCamera(`/World/MEP____/Cameras/${cameraName}`);
                    return; // Don't send the regular selection message for cameras
                }
            }
        }
        
        // Regular selection logic for non-camera prims
        const paths: string[] = Array.from(selectedUsdPrims).map(obj => obj.path);
        const message: AppStreamMessageType = {
            event_type: "selectPrimsRequest",
            payload: {
                paths: paths
            }
        };
        AppStream.sendMessage(JSON.stringify(message));

        selectedUsdPrims.forEach(usdPrim => {this._onFillUSDPrim(usdPrim)});
    }

    /**
    * @function _onStageReset
    *
    * Clears the selection and sends a request to reset the stage to how it was at the time it loaded.
    */
    private _onStageReset (): void {
        this.setState({ selectedUSDPrims: new Set<USDPrimType>() });
        const selection_message: AppStreamMessageType = {
            event_type: "selectPrimsRequest",
            payload: {
                paths: []
            }
        };
        AppStream.sendMessage(JSON.stringify(selection_message));

        const reset_message: AppStreamMessageType = {
            event_type: "resetStage",
            payload: {}
        };
        AppStream.sendMessage(JSON.stringify(reset_message));
    }

    /**
    * @function _onFillUSDPrim
    *
    * If the usdPrim has a children property a request is sent for its children.
    * When the streaming app sends an empty children value it is not an array.
    * When a prim does not have children the streaming app does not provide a children
    * property to begin with.
    */
    private _onFillUSDPrim (usdPrim: USDPrimType): void {
        if (usdPrim !== null && "children" in usdPrim && !Array.isArray(usdPrim.children)) {
            this._getChildren(usdPrim);
        }
    }
    
    /**
    * @function _findUSDPrimByPath
    *
    * Recursive search for a USDPrimType object by path.
    */
    private _findUSDPrimByPath (path: string, array: USDPrimType[] = this.state.usdPrims): USDPrimType | null {
        if (Array.isArray(array)) {
            for (const obj of array) {
                if (obj.path === path) {
                    return obj;
                }
                if (obj.children && obj.children.length > 0) {
                    const found = this._findUSDPrimByPath(path, obj.children);
                    if (found) {
                        return found;
                    }
                }
            }
        }
        return null;
    }
    
    /**
    * @function _handleCustomEvent
    *
    * Handle message from stream.
    */
    private _handleCustomEvent (event: any): void {
        if (!event) {
            return;
        }

        // response received once a USD asset is fully loaded
        if (event.event_type === "openedStageResult") {
            if (event.payload.result === "success") {
                this._queryLoadingState() 
            }
            else {
                console.error('Kit App communicates there was an error loading: ' + event.payload.url);
            }
        }
        
        // response received from the 'loadingStateQuery' request
        else if (event.event_type == "loadingStateResponse") {
            // loadingStateRequest is used to poll Kit for proof of life.
            // For the first loadingStateResponse we set isKitReady to true
            // and run one more query to find out what the current loading state
            // is in Kit
            if (this.state.isKitReady === false) {
                console.info("Kit is ready to load assets")
                this.setState({ isKitReady: true })
                this._queryLoadingState()
            }
            
            else {
                const usdAsset: USDAssetType = this._getAsset(event.payload.url)
                const isStageValid: boolean = !!(usdAsset.name && usdAsset.url)
                
                // set the USD Asset dropdown to the currently opened stage if it doesn't match
                if (isStageValid && usdAsset !== undefined && this.state.selectedUSDAsset !== usdAsset)
                    this.setState({ selectedUSDAsset: usdAsset })

                // if the stage is empty, force-load the selected usd asset; the loading state is irrelevant
                if (!event.payload.url)
                    this._openSelectedAsset()
                
                // if a stage has been fully loaded and isn't a part of this application, force-load the selected stage
                else if (!isStageValid && event.payload.loading_state === "idle"){
                    console.log(`The loaded asset ${event.payload.url} is invalid.`)
                    this._openSelectedAsset()
                }
                
                // show stream and populate children if the stage is valid and it's done loading
                if (isStageValid && event.payload.loading_state === "idle")
                {
                    this._getChildren()
                    this.setState({ showStream: true, loadingText: "Asset loaded", showUI: true, isLoading: false })
                }
            }
        }
        
        // Loading progress amount notification.
        else if (event.event_type === "updateProgressAmount") {
            console.log('Kit App communicates progress amount.');
        }
            
        // Loading activity notification.
        else if (event.event_type === "updateProgressActivity") {
            console.log('Kit App communicates progress activity.');
            if (this.state.loadingText !== "Loading Asset...")
                this.setState( {loadingText: "Loading Asset...", isLoading: true} )
        }
            
        // Notification from Kit about user changing the selection via the viewport.
        else if (event.event_type === "stageSelectionChanged") {
            console.log('Selection changed:', event.payload.prims);
            
            if (!Array.isArray(event.payload.prims) || event.payload.prims.length === 0) {
                console.log('Kit App communicates an empty stage selection.');
                this.setState({ 
                    selectedUSDPrims: new Set<USDPrimType>(),
                    showPiPanel: false,
                    selectedObjectPath: ""
                });
            }
            else {
                console.log('Kit App communicates selection of objects:', event.payload.prims);
                const selectedPath = event.payload.prims[0]; // Get first selected object path
                
                // DEBUG: Log all clicked paths
                console.log('*** CLICKED OBJECT PATH: ***', selectedPath);
                
                // Check if we're in a P5 camera view AND the MEP_Schneider asset is loaded
                if (this._isMEPSchneiderAsset() && this._isInP5CameraView()) {
                    console.log('*** OBJECT CLICKED IN P5 CAMERA VIEW! Showing PI data panel... ***');
                    this.setState({ 
                        selectedObjectPath: selectedPath,
                        showPiPanel: true
                    });
                    this._fetchPIData();
                } else {
                    // Hide PI panel if not in P5 camera view or not MEP_Schneider
                    this.setState({ 
                        showPiPanel: false,
                        selectedObjectPath: ""
                    });
                }
                
                // Update the normal USD selection UI
                const usdPrimsToSelect: Set<USDPrimType> = new Set<USDPrimType>();
                event.payload.prims.forEach((objPath: string) => {
                    const result = this._findUSDPrimByPath(objPath);
                    if (result !== null) {
                        usdPrimsToSelect.add(result);
                    }
                });
                this.setState({ selectedUSDPrims: usdPrimsToSelect });
            }
        }
        // Streamed app provides children of a parent USDPrimType
        else if (event.event_type === "getChildrenResponse") {
            console.log('Kit App sent stage prims');
            const prim_path = event.payload.prim_path;
            const children = event.payload.children;
            const usdPrim = this._findUSDPrimByPath(prim_path);
            if (usdPrim === null) {
                this.setState({ usdPrims: children });
            }
            else {
                usdPrim.children = children;
                this.setState({ usdPrims: this.state.usdPrims });
            }
            if (Array.isArray(children)){
                this._makePickable(children);
            }
        }
        // Camera switching response - UPDATED
        else if (event.event_type === "switchCameraResponse") {
            if (event.payload.result === "success") {
                console.log(`Successfully switched to camera: ${event.payload.camera_path}`);
                // Update UI state to reflect camera change
                if (event.payload.camera_path === "FREE_CAMERA") {
                    this.setState({ selectedCamera: "" });
                } else {
                    this.setState({ selectedCamera: event.payload.camera_path });
                }
            } else {
                console.error(`Failed to switch camera: ${event.payload.error}`);
            }
        }
        // other messages from app to kit
        else if (event.messageRecipient === "kit") {
            console.log("onCustomEvent");
            console.log(JSON.parse(event.data).event_type);
        }
    }

    /**
    * @function _handleAppStreamFocus
    *
    * Update state when AppStream is in focus.
    */
    private _handleAppStreamFocus (): void {
        console.log('User is interacting in streamed viewer');
    }

    /**
    * @function _handleAppStreamBlur
    *
    * Update state when AppStream is not in focus.
    */
    private _handleAppStreamBlur (): void {
        console.log('User is not interacting in streamed viewer');
    }
    
    render() {
        const sidebarWidth = 300;
        const piPanelWidth = 350;
        
        return (
            <div
                style={{
                    position: 'absolute',
                    top: headerHeight,
                    width: '100%',
                    height: '100%'
                }}
            >
                <div style={{
                            position: 'absolute',
                            height: `calc(100% - ${headerHeight}px)`,
                            width: `calc(100% - ${sidebarWidth}px - ${this.state.showPiPanel ? piPanelWidth : 0}px)`
                }}>
                    
                {/* Loading text indicator */}
                {!this.state.showStream && 
                    <div className="loading-indicator-label">
                        {this.state.loadingText}
                        <div className="spinner-border" role="status" style={{ marginTop: 10, visibility: this.state.isLoading? 'visible': 'hidden' }} />
                    </div>
                }

                {/* Camera Selector for MEP_Schneider - UPDATED */}
                {this._isMEPSchneiderAsset() && this.state.showUI && (
                    <CameraSelector
                        visible={this.state.showStream}
                        onCameraSelect={(cameraPath) => this._switchCamera(cameraPath)}
                        selectedCamera={this.state.selectedCamera}
                    />
                )}

                {/* Streamed app */}
                <AppStream
                    sessionId={this.props.sessionId}
                    backendUrl={this.props.backendUrl}
                    signalingserver={this.props.signalingserver}
                    signalingport={this.props.signalingport}
                    mediaserver={this.props.mediaserver}
                    mediaport={this.props.mediaport}
                    accessToken={this.props.accessToken}
                    onStarted={() => this._onStreamStarted()}
                    onFocus={() => this._handleAppStreamFocus()}
                    onBlur={() => this._handleAppStreamBlur()}
                    style={{
                        position: 'relative',
                        visibility: this.state.showStream? 'visible' : 'hidden'
                    }}
                    onLoggedIn={(userId) => this._onLoggedIn(userId)}
                    handleCustomEvent={(event) => this._handleCustomEvent(event)}
                    onStreamFailed={this.props.onStreamFailed}
                    />
                </div>

                {this.state.showUI &&
                <>
                        
                    {/* USD Asset Selector */}
                    <USDAsset
                        usdAssets={this.state.usdAssets}
                        selectedAssetUrl={this.state.selectedUSDAsset?.url}
                        onSelectUSDAsset={(value) => this._onSelectUSDAsset(value)}
                        width={sidebarWidth}
                    />
                    {/* USD Stage Listing */}
                    <USDStage
                        ref={this.usdStageRef}
                        width={sidebarWidth}
                        usdPrims={this.state.usdPrims}
                        onSelectUSDPrims={(value) => this._onSelectUSDPrims(value)}
                        selectedUSDPrims={this.state.selectedUSDPrims}
                        fillUSDPrim={(value) => this._onFillUSDPrim(value)}
                        onReset={() => this._onStageReset()}
                        />
                    </>
                }

                {/* PI Data Panel */}
                {this.state.showPiPanel && (
                    <PIDataPanel
                        width={piPanelWidth}
                        piData={this.state.piData}
                        onClose={this._closePIPanel}
                        onRefresh={this._refreshPIData}
                        selectedObjectPath={this.state.selectedObjectPath}
                    />
                )}
            </div>
            );
        }
    }