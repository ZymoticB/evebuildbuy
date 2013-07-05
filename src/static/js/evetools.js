angular.module('evetools', []).config(function($routeProvider) {
	$routeProvider.
		when('/', {controller:MainCtrl, templateUrl:'main.html'}).
		when('/item', {controller:ItemCtrl, templateUrl:'item.html'}).
		when('/contact', {controller:ContactCtrl, templateUrl:'contact.html'}).
		otherwise({redirectTo:'/'});
	});

function ContactCtrl($scope){
}

function MainCtrl($scope){
}

function ItemCtrl($scope) {
	$scope.itemME = 0;
	$scope.partME = 0;
}
