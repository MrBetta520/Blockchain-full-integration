// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import "forge-std/Script.sol";
import "forge-std/console.sol";
import "../src/Source.sol";
import "../src/Destination.sol";

contract Deploy is Script {
    
    // ERC20 token addresses from erc20s.csv
    address[] erc20Tokens = [
        0xc677c31AD31F73A5290f5ef067F8CEF8d301e45c,
        0x0773b81e0524447784CcE1F3808fed6AaA156eC8
    ];

    function run() external {
        // Get private key from environment variable
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);
        
        console.log("Deploying contracts with account:", deployer);
        console.log("Chain ID:", block.chainid);

        vm.startBroadcast(deployerPrivateKey);

        if (block.chainid == 43113) {
            // Avalanche testnet - Deploy Source contract
            deploySourceContract(deployer);
        } else if (block.chainid == 97) {
            // BSC testnet - Deploy Destination contract  
            deployDestinationContract(deployer);
        } else {
            console.log("Unsupported chain ID:", block.chainid);
            return;
        }

        vm.stopBroadcast();
    }

    function deploySourceContract(address admin) internal {
        console.log("\n=== Deploying Source Contract on Avalanche ===");
        
        Source source = new Source(admin);
        console.log("Source contract deployed to:", address(source));

        // Register tokens
        console.log("\n=== Registering Tokens on Source ===");
        for (uint i = 0; i < erc20Tokens.length; i++) {
            address token = erc20Tokens[i];
            
            // Check if already registered
            if (!source.approved(token)) {
                source.registerToken(token);
                console.log("Token registered:", token);
            } else {
                console.log("Token already registered:", token);
            }
        }

        console.log("\n=== Source Deployment Complete ===");
        console.log("Source Contract Address:", address(source));
        console.log("Save this address to your contract_info.json file");
    }

    function deployDestinationContract(address admin) internal {
        console.log("\n=== Deploying Destination Contract on BSC ===");
        
        Destination destination = new Destination(admin);
        console.log("Destination contract deployed to:", address(destination));

        // Create wrapped tokens
        console.log("\n=== Creating Wrapped Tokens on Destination ===");
        for (uint i = 0; i < erc20Tokens.length; i++) {
            address token = erc20Tokens[i];
            
            // Check if wrapped token already exists
            if (destination.wrapped_tokens(token) == address(0)) {
                string memory name = string(abi.encodePacked("Wrapped Token ", vm.toString(i + 1)));
                string memory symbol = string(abi.encodePacked("WT", vm.toString(i + 1)));
                
                address wrappedToken = destination.createToken(token, name, symbol);
                console.log("Wrapped token created for", token);
                console.log("Wrapped token address:", wrappedToken);
            } else {
                console.log("Wrapped token already exists for:", token);
            }
        }

        console.log("\n=== Destination Deployment Complete ===");
        console.log("Destination Contract Address:", address(destination));
        console.log("Save this address to your contract_info.json file");
    }
}